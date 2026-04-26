from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import sys

sys.dont_write_bytecode = True

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import argparse
import sqlite3
import time

import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split

from utils.data import Data
from utils.map import Mapping
from utils.model import Decoder, Encoder
from utils.params import common_paths, train_params, word2vec_params
from utils.training_dataset import (
    dataset_to_training_pairs,
    load_attack_log_samples,
    load_samples,
    normalize_training_row,
    save_samples,
)

from gensim.models import KeyedVectors
from gensim.models import word2vec

import logging
import warnings

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
warnings.simplefilter(action="ignore", category=FutureWarning)
warnings.simplefilter(action="ignore", category=Warning)
tf.get_logger().setLevel(logging.ERROR)
tf.autograph.set_verbosity(0)

physical_devices = tf.config.experimental.list_physical_devices("GPU")
if len(physical_devices) > 0:
    for k in range(len(physical_devices)):
        tf.config.experimental.set_memory_growth(physical_devices[k], True)
        print("[*] memory growth:", tf.config.experimental.get_memory_growth(physical_devices[k]))
else:
    print("[-] Not enough GPU hardware devices available.")


def create_mapping_table(dir_path, map_obj):
    """Rebuild mapping_table so runtime has the current vocabulary, including <UNK>."""
    conn = sqlite3.connect(dir_path + common_paths["response_db"])
    c = conn.cursor()
    c.execute("create table if not exists mapping_table(id int, word text, UNIQUE(id, word))")
    c.execute("delete from mapping_table")

    for key, value in map_obj.items():
        c.execute("insert or ignore into mapping_table values(?, ?)", (value, key))

    c.execute("select max(res_id) from response_table")
    max_id = c.fetchall()[0][0]
    if max_id is not None and max_id >= train_params["max_index"]:
        train_params["max_index"] = max_id + 1

    conn.commit()
    conn.close()


def build_synthetic_dataset():
    return [
        normalize_training_row(
            "GET",
            "/",
            "<EMP>",
            {"Host": "localhost", "User-Agent": "curl/7.0"},
            "<EMP>",
            0,
            source="synthetic",
            attack_tags=["normal"],
        ),
        normalize_training_row(
            "GET",
            "/admin",
            "<EMP>",
            {"Host": "localhost", "User-Agent": "curl/7.0"},
            "<EMP>",
            1,
            source="synthetic",
            attack_tags=["web_probe"],
        ),
        normalize_training_row(
            "POST",
            "/login",
            "<EMP>",
            {"Host": "localhost", "Content-Type": "application/x-www-form-urlencoded"},
            "username=admin&password=admin",
            2,
            source="synthetic",
            attack_tags=["normal"],
        ),
        normalize_training_row(
            "GET",
            "/cgi-bin/luci",
            "<EMP>",
            {"Host": "localhost", "User-Agent": "sqlmap"},
            "<EMP>",
            3,
            source="synthetic",
            attack_tags=["scanner"],
        ),
    ]


def ensure_default_response_rows(response_db_path):
    conn = sqlite3.connect(response_db_path)
    c = conn.cursor()
    c.execute(
        """
        create table if not exists response_table(
            res_id int,
            res_status int,
            res_headers text,
            res_body blob,
            UNIQUE(res_status, res_headers, res_body)
        )
        """
    )
    defaults = [
        (0, 200, "Content-Type: text/html; charset=utf-8@@@Connection: close", b"<html><body><h1>FirmPot</h1></body></html>"),
        (1, 403, "Content-Type: text/html; charset=utf-8@@@Connection: close", b"<html><body><h1>403 Forbidden</h1></body></html>"),
        (2, 302, "Location: /cgi-bin/luci@@@Set-Cookie: session_id=demo; Path=/", b""),
        (3, 200, "Content-Type: text/html; charset=utf-8@@@Connection: close", b"<html><body><h1>LuCI</h1></body></html>"),
    ]
    for row in defaults:
        c.execute("insert or ignore into response_table values(?, ?, ?, ?)", row)
    conn.commit()
    conn.close()


def sync_learning_table(db_path, samples):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """
        create table if not exists learning_table(
            req_method text,
            req_path text,
            req_query text,
            req_headers text,
            req_body text,
            res_id int,
            UNIQUE(req_method, req_path, req_query, req_headers, req_body)
        )
        """
    )

    for sample in samples:
        c.execute(
            "insert or ignore into learning_table values(?, ?, ?, ?, ?, ?)",
            (
                sample["method"],
                sample["path"],
                sample["query"],
                sample["headers"],
                sample["body"],
                int(sample["res_id"]),
            ),
        )

    conn.commit()
    conn.close()


def load_fuzz_samples(args, learning_db_path):
    dataset_path = args.dataset
    if args.reuse_data and os.path.exists(dataset_path):
        print("[*] Loading cached fuzz dataset from", dataset_path)
        return load_samples(dataset_path)

    if os.path.exists(learning_db_path):
        conn = sqlite3.connect(learning_db_path)
        c = conn.cursor()
        c.execute(
            "select req_method, req_path, req_query, req_headers, req_body, res_id from learning_table"
        )
        rows = c.fetchall()
        conn.close()
        if rows:
            samples = [normalize_training_row(*row, source="fuzz") for row in rows]
            save_samples(dataset_path, samples)
            print("[*] Saved fuzz dataset to", dataset_path)
            return samples

    return []


def load_training_samples(args, learning_db_path):
    fuzz_samples = load_fuzz_samples(args, learning_db_path)
    log_samples = load_attack_log_samples(args.log_dir, default_res_id=0)
    if log_samples:
        print("[*] Loaded", len(log_samples), "samples from honeypot logs")

    final_dataset = fuzz_samples + log_samples
    if not final_dataset:
        print("[!] No scanner or log dataset found. Seeding synthetic baseline samples.")
        final_dataset = build_synthetic_dataset()

    save_samples(args.training_dataset, final_dataset)
    sync_learning_table(learning_db_path, final_dataset)
    return final_dataset


def get_model(word2vec_path, req_data=None, force_retrain=False):
    """Load a cached word2vec model or train one from request data."""
    if not force_retrain and os.path.exists(word2vec_path):
        print("[*] Load cached word2vec model from", word2vec_path)
        return KeyedVectors.load_word2vec_format(
            word2vec_path, binary=True, unicode_errors="ignore"
        )

    if req_data is None:
        raise FileNotFoundError(word2vec_path)

    print("[*] Training word2vec model:", word2vec_path)
    w2v_data = []
    for raw in req_data:
        raw = list(raw)
        tmp = [raw[0], raw[1], raw[2], raw[4], "<UNK>"]
        for header in raw[3].split("@@@"):
            tmp.append(header)
        while len(tmp) < train_params["max_input_len"]:
            tmp.append("<PAD>")
        tmp.append("<END>")
        w2v_data.append(tmp)

    model = word2vec.Word2Vec(
        sentences=w2v_data,
        size=train_params["embed_size"],
        window=word2vec_params["window"],
        min_count=word2vec_params["min_count"],
        iter=word2vec_params["iter"],
        workers=word2vec_params["workers"],
    )
    os.makedirs(os.path.dirname(word2vec_path), exist_ok=True)
    model.wv.save_word2vec_format(word2vec_path, binary=True)
    return model


def get_embedding_matrix(model, mapping, mapping_size):
    if hasattr(model, "vector_size"):
        vector_size = model.vector_size
    else:
        vector_size = model.wv.vector_size

    embedding_matrix = np.zeros((mapping_size, vector_size), dtype="float32")
    lookup = model if hasattr(model, "key_to_index") else model.wv

    for word, idx in mapping.items():
        try:
            embedding_matrix[idx] = lookup[word]
        except KeyError:
            if word == "<UNK>":
                embedding_matrix[idx] = np.random.normal(0, 0.1, vector_size)

    return embedding_matrix


def loss_function(real, pred):
    mask = tf.math.logical_not(tf.math.equal(real, 0))
    loss_ = loss_object(real, pred)
    mask = tf.cast(mask, dtype=loss_.dtype)
    loss_ *= mask
    return tf.reduce_mean(loss_)


@tf.function
def train_step(inputs, targets, enc_hidden):
    loss = 0
    with tf.GradientTape() as tape:
        enc_output, enc_hidden = encoder(inputs, enc_hidden)
        dec_hidden = enc_hidden
        dec_input = tf.expand_dims([0] * train_params["batch_size"], 1)

        for t in range(0, targets.shape[1]):
            predictions, dec_hidden, _ = decoder(dec_input, dec_hidden, enc_output)
            loss += loss_function(targets[:, t], predictions)
            dec_input = tf.expand_dims(targets[:, t], 1)

    batch_loss = loss / int(targets.shape[1])
    variables = encoder.trainable_variables + decoder.trainable_variables
    gradients = tape.gradient(loss, variables)
    optimizer.apply_gradients(zip(gradients, variables))
    return predictions, batch_loss


def safe_predict(request):
    try:
        return predict(request)
    except Exception as e:
        print("[!] Prediction failed during evaluation:", e)
        return [0]


def predict(request):
    inputs = tf.keras.preprocessing.sequence.pad_sequences(
        [request], maxlen=train_params["max_input_len"], padding="post"
    )
    inputs = tf.convert_to_tensor(inputs)

    result = []
    hidden = [tf.zeros((1, train_params["hidden_size"]))]
    enc_out, enc_hidden = encoder(inputs, hidden)

    dec_hidden = enc_hidden
    dec_input = tf.expand_dims([0], 0)

    for _ in range(1):
        predictions, dec_hidden, _ = decoder(dec_input, dec_hidden, enc_out)
        predicted_id = tf.argmax(predictions[0]).numpy()
        result.append(predicted_id)
        dec_input = tf.expand_dims([predicted_id], 0)

    return result


def evaluate(req_test, res_test):
    if not req_test:
        print("[!] No evaluation samples available.")
        return

    mistake = 0
    for request, response in zip(req_test, res_test):
        prediction = safe_predict(request)
        expected = list(response)
        if expected != prediction:
            mistake += 1

    print("[*] Percentage of Collect : {0:.2%}".format((len(req_test) - mistake) / len(req_test)))
    print("[*] Percentage of Mistake : {0:.2%}".format(mistake / len(req_test)))


def validation_loss(req_val, res_val):
    if not req_val:
        return 0.0

    total = 0.0
    for request, response in zip(req_val, res_val):
        predicted = safe_predict(request)[0]
        total += 0.0 if predicted == response[0] else 1.0
    return total / len(req_val)


def main():
    print("[*] Start Training")
    start_time = time.time()

    best_val = float("inf")
    patience = 0
    epochs_num = train_params["epoch_num"]
    steps_num = max(1, len(req_train.data) // train_params["batch_size"])

    for epoch in range(epochs_num):
        start = time.time()
        enc_hidden = encoder.initialize_hidden_state()
        total_loss = 0.0

        for batch, (inputs, targets) in enumerate(dataset.take(steps_num)):
            predictions, batch_loss = train_step(inputs, targets, enc_hidden)
            total_loss += float(batch_loss.numpy())

            if batch % 100 == 0:
                print("Epoch {} Batch {} Loss {:.4f}".format(epoch + 1, batch, batch_loss.numpy()))

        if (epoch + 1) % 2 == 0:
            checkpoint.save(file_prefix=checkpoint_prefix)

        avg_loss = total_loss / max(1, steps_num)
        val_error = validation_loss(req_val.data, res_val.data)
        print("[*] Epoch {} Loss {:.4f}".format(epoch + 1, avg_loss))
        print("[*] Epoch {} ValError {:.4f}".format(epoch + 1, val_error))
        print("[*] Time taken for 1 epoch {} sec\n".format(time.time() - start))

        if val_error + 1e-6 < best_val:
            best_val = val_error
            patience = 0
            checkpoint.save(file_prefix=checkpoint_prefix)
        else:
            patience += 1
            if patience >= train_params["early_stopping_patience"]:
                print("[*] Early stopping triggered after {} epochs".format(epoch + 1))
                break

    print("[*] Finish :", time.time() - start_time)
    print("[*] Start Evaluation")
    evaluate(req_test.data, res_test.data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Learn the web interaction.")
    parser.add_argument(
        "-d",
        "--directory",
        default=common_paths["directory"],
        help="Specify the directory where the database is stored.",
    )
    parser.add_argument(
        "-w",
        "--word2vec",
        default="",
        help="Specify the path to the word2vec model you want to load.",
    )
    parser.add_argument(
        "-s",
        "--split",
        type=float,
        default=0.9,
        help="Train/test split ratio (default: 0.9).",
    )
    parser.add_argument(
        "--reuse-data",
        action="store_true",
        help="Reuse the cached fuzz dataset instead of rebuilding it from scanning output.",
    )
    parser.add_argument(
        "--retrain",
        action="store_true",
        help="Force retraining the cached word2vec model.",
    )
    parser.add_argument(
        "--dataset",
        default=os.path.join(common_paths["directory"], common_paths["fuzz_dataset"]),
        help="Path to the cached fuzz dataset.",
    )
    parser.add_argument(
        "--training-dataset",
        default=os.path.join(common_paths["directory"], common_paths["training_dataset"]),
        help="Path to save the merged fuzz + log dataset.",
    )
    parser.add_argument(
        "--log-dir",
        default=os.path.join(repo_root, "honeypot_instance", "logs"),
        help="Directory containing honeypot logs to merge into training data.",
    )
    args = parser.parse_args()

    dir_path = args.directory
    if not os.path.exists(dir_path):
        print("[-] The directory path specified in the argument does not exist.")
        sys.exit(1)
    if not dir_path.endswith("/"):
        dir_path = dir_path + "/"

    if not os.path.isabs(args.dataset):
        args.dataset = os.path.normpath(os.path.join(repo_root, args.dataset))
    if not os.path.isabs(args.training_dataset):
        args.training_dataset = os.path.normpath(os.path.join(repo_root, args.training_dataset))

    learning_db_path = dir_path + common_paths["learning_db"]
    response_db_path = dir_path + common_paths["response_db"]
    os.makedirs(dir_path, exist_ok=True)
    os.makedirs(os.path.join(dir_path, common_paths["data_dir"]), exist_ok=True)
    ensure_default_response_rows(response_db_path)

    samples = load_training_samples(args, learning_db_path)
    req_data, res_data = dataset_to_training_pairs(samples)

    if len(req_data) < 4 or len(res_data) < 4:
        synthetic = build_synthetic_dataset()
        samples.extend(synthetic)
        save_samples(args.training_dataset, samples)
        sync_learning_table(learning_db_path, synthetic)
        req_data, res_data = dataset_to_training_pairs(samples)

    map_obj = Mapping(learning_db_path)
    train_params["mapping"] = map_obj.mapping
    train_params["max_index"] = map_obj.mapping_size
    create_mapping_table(dir_path, train_params["mapping"])

    train_size = min(max(args.split, 0.5), 0.95)
    if len(req_data) < 3:
        req_train = req_data
        req_test = req_data
        res_train = res_data
        res_test = res_data
    else:
        req_train, req_test, res_train, res_test = train_test_split(
            req_data,
            res_data,
            train_size=train_size,
            shuffle=True,
            random_state=42,
        )

    if len(req_train) > 2:
        req_train, req_val, res_train, res_val = train_test_split(
            req_train,
            res_train,
            test_size=train_params["validation_split"],
            shuffle=True,
            random_state=42,
        )
    else:
        req_val, res_val = req_test, res_test

    print("[*] size of train data :", len(req_train))
    print("[*] size of validation data :", len(req_val))
    print("[*] size of test data :", len(req_test))

    effective_batch_size = max(1, min(train_params["batch_size"], len(req_train)))
    train_params["batch_size"] = effective_batch_size

    req_train = Data(req_train, map_obj, is_request=True)
    req_val = Data(req_val, map_obj, is_request=True)
    req_test = Data(req_test, map_obj, is_request=True)
    res_train = Data(res_train, map_obj, is_request=False)
    res_val = Data(res_val, map_obj, is_request=False)
    res_test = Data(res_test, map_obj, is_request=False)

    req_gen = req_train.padded_numpy_generator()
    res_gen = res_train.padded_numpy_generator()
    dataset = tf.data.Dataset.from_tensor_slices((req_gen, res_gen)).shuffle(len(req_gen)).batch(
        train_params["batch_size"], drop_remainder=True
    )

    word2vec_path = args.word2vec if args.word2vec else dir_path + common_paths["word2vec"]
    word2vec_model = get_model(word2vec_path, req_data, force_retrain=args.retrain)
    embedding_matrix = get_embedding_matrix(
        word2vec_model, train_params["mapping"], train_params["max_index"]
    )

    checkpoints_dir = "./" + dir_path + common_paths["checkpoints"]
    os.makedirs(checkpoints_dir, exist_ok=True)
    train_params["checkpoints"] = checkpoints_dir

    encoder = Encoder(
        train_params["max_index"],
        train_params["embed_size"],
        train_params["hidden_size"],
        train_params["batch_size"],
        embedding_matrix,
    )
    decoder = Decoder(
        train_params["max_index"],
        train_params["embed_size"],
        train_params["hidden_size"],
        train_params["batch_size"],
    )

    optimizer = tf.keras.optimizers.Adam()
    loss_object = tf.keras.losses.SparseCategoricalCrossentropy(
        from_logits=True, reduction="none"
    )

    checkpoint_prefix = os.path.join(checkpoints_dir, "ckpt")
    checkpoint = tf.train.Checkpoint(
        optimizer=optimizer,
        encoder=encoder,
        decoder=decoder,
    )

    main()
