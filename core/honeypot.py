
#------------------------------------------------
# Import 
#------------------------------------------------

from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals 
from __future__ import division

import os
import sys
sys.dont_write_bytecode = True

current_dir = os.path.abspath(os.path.dirname(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

repo_root = os.path.abspath(os.path.join(current_dir, ".."))
if repo_root not in sys.path:
    sys.path.insert(1, repo_root)

import argparse
import json
import time

import traceback
import threading
import socket

import tensorflow as tf
import numpy as np

import sqlite3
import difflib
from gensim.models import KeyedVectors

import logging
import logging.handlers
import warnings
import shutil

import select
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

# My program
from utils.oov import MagnitudeOOV
from utils.model import Encoder, Decoder
from utils.params import common_paths, train_params, hardware_info
from utils.http_headers import check_req_header, get_shaped_header
from rl_agent import RLAgent
from detection import AttackDetector
from logger import StructuredLogger
from metrics import get_metrics
from session_manager import SessionManager


#------------------------------------------------
# GPU
#------------------------------------------------

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=Warning)
tf.get_logger().setLevel('INFO')
tf.autograph.set_verbosity(0)
tf.get_logger().setLevel(logging.ERROR)

physical_devices = tf.config.experimental.list_physical_devices('GPU')
if len(physical_devices) > 0:
    for k in range(len(physical_devices)):
        tf.config.experimental.set_memory_growth(physical_devices[k], True)
        print("[*] memory growth:", tf.config.experimental.get_memory_growth(physical_devices[k]))
else:
    print("[-] Not enough GPU hardware devices available.")

#------------------------------------------------
# Information
#------------------------------------------------

# Timezone
JST = timezone(timedelta(hours=+9), 'JST')

# Server
ip = "0.0.0.0"
port = 8080

honeypot_ip = socket.gethostbyname(socket.gethostname())

# Connection timeout
timeout = 5.0

#------------------------------------------------
# Define Model
#------------------------------------------------

def get_model(word2vec_path=None):

    # Model
    encoder = Encoder(train_params["max_index"], train_params["embed_size"], train_params["hidden_size"], train_params["batch_size"])
    decoder = Decoder(train_params["max_index"], train_params["embed_size"], train_params["hidden_size"], train_params["batch_size"])

    # Optimizer
    optimizer = tf.keras.optimizers.Adam()

    # Checkpoints
    train_params["checkpoints"] = common_paths["checkpoints"]
    checkpoint = tf.train.Checkpoint(optimizer=optimizer,
                                    encoder=encoder,
                                    decoder=decoder)
    # Load checkpoint
    latest_checkpoint = tf.train.latest_checkpoint(train_params['checkpoints'])
    if latest_checkpoint:
        checkpoint.restore(latest_checkpoint)
    else:
        print("[!] No checkpoints found. Starting with fallback model weights.")


    if word2vec_path is None:
        return encoder, decoder
    else:
        model = KeyedVectors.load_word2vec_format(word2vec_path, binary=True, unicode_errors='ignore')
        moov = MagnitudeOOV(word2vec=model)
        return moov, encoder, decoder

#------------------------------------------------
# Prediction Functions
#------------------------------------------------

def get_similar_idx(req):

    simularity = 0
    simular_str = "<EMP>"

    for key in mapping:
        rate = difflib.SequenceMatcher(None, req, key).ratio()    
        if rate > simularity:
            simularity = rate
            simular_str = key

    return mapping[simular_str]

def string_to_int(request_list, is_magnitude=False):

    idx_list = []
    oov_list = []
    
    if is_magnitude:
        for i, req in enumerate(request_list):
            try:
                idx_list.append(mapping[req])
            except:
                idx_list.append(0)
                oov_list.append((i, req))
                
    else:
        for i, req in enumerate(request_list):
            try:
                idx_list.append(mapping[req])
            except:
                idx_list.append(get_similar_idx(req))


    return idx_list, oov_list

def predict(idx_list, oov_list=None, moov=None, k=1):

    inputs = tf.keras.preprocessing.sequence.pad_sequences([idx_list],
                                                           maxlen=train_params["max_input_len"],
                                                           padding='post')
    
    inputs = tf.convert_to_tensor(inputs)

    result = []

    hidden = [tf.zeros((1, train_params["hidden_size"]))]
    if oov_list is None:
        enc_out, enc_hidden = encoder(inputs, hidden)
    else:
        enc_out, enc_hidden = encoder(inputs, hidden, oov_list, moov)

    dec_hidden = enc_hidden
    dec_input = tf.expand_dims([0], 0)

    for t in range(1):
        predictions, dec_hidden, attention_weights = decoder(dec_input,
                                                             dec_hidden,
                                                             enc_out)

        if k == 1:
            predicted_id = tf.argmax(predictions[0]).numpy()
            result.append(predicted_id)
            dec_input = tf.expand_dims([predicted_id], 0)
        else:
            top_k = tf.nn.top_k(predictions[0], k)
            result.extend(top_k.indices.numpy().tolist())
            dec_input = tf.expand_dims([result[0]], 0)

    return result

#------------------------------------------------
# Replace Function
#------------------------------------------------

def replace_str(string, hardware_info):

    for key, value in hardware_info.items():
        string = string.replace(key, value)

    dt = datetime.now()

    string = string.replace("DATEINFO", dt.strftime('%Y-%m-%d'))
    string = string.replace("TIMEINFO", dt.strftime('%H:%M:%S'))
    string = string.replace("IPINFO", honeypot_ip)

    return string


#------------------------------------------------
# Logging Function
#------------------------------------------------

# Access log
def logging_access(log):
    with open(accesslog, 'a') as f: # to file
        f.write(log)

# Honeypot log
def logging_system(message, is_error, is_exit):

    if not is_error: #CYAN
        print("\u001b[36m[INFO]{0}\u001b[0m".format(message))

        with open(honeypotlog, 'a') as f: # to file
            f.write("[{0}][INFO]{1}\n".format(get_time(), message))

    else: #RED
        print("\u001b[31m[ERROR]{0}\u001b[0m".format(message))
        with open(honeypotlog, 'a') as f: # to file
            f.write("[{0}][ERROR]{1}\n".format(get_time(), message))
        
    if is_exit:
        sys.exit(1)

def get_time():
    return "{0:%Y-%m-%d %H:%M:%S%z}".format(datetime.now(JST))


def get_default_response():
    """Return a minimal safe HTTP response when the response DB has no usable rows."""
    headers = "Content-Type: text/html; charset=utf-8@@@Connection: close"
    body = b"<html><body><h1>FirmPot</h1><p>Fallback response active.</p></body></html>"
    return 200, headers, body


def get_usable_response(cursor, res_id):
    """Return a real HTTP response row, ignoring scanner sentinel status 599."""
    try:
        cursor.execute(
            'select res_status, res_headers, res_body from response_table where res_id = ?',
            (res_id,),
        )
        response_row = cursor.fetchone()
    except Exception:
        response_row = None

    if response_row is not None and response_row[0] != 599:
        return response_row

    try:
        cursor.execute(
            '''
            select res_status, res_headers, res_body
            from response_table
            where res_status between 200 and 499
            order by
                case when res_status = 200 then 0 else 1 end,
                length(res_body) desc
            limit 1
            '''
        )
        fallback_row = cursor.fetchone()
    except Exception:
        fallback_row = None

    if fallback_row is not None:
        return fallback_row

    return get_default_response()


def ensure_runtime_modules():
    """Copy support modules into the generated instance if they are missing."""
    required_files = [
        "detection.py",
        "logger.py",
        "metrics.py",
        "session_manager.py",
    ]
    for filename in required_files:
        if os.path.exists(filename):
            continue
        source = os.path.join("..", filename)
        if os.path.exists(source):
            shutil.copy(source, filename)
            print(f"[!] Restored missing runtime module from {source}")

#------------------------------------------------
# Honeypot Server
#------------------------------------------------

class HoneypotHTTPServer(HTTPServer):

    def server_bind(self):
        HTTPServer.server_bind(self)
        self.socket.settimeout(timeout)

    def finish_request(self, request, client_address):
        request.settimeout(timeout)
        HTTPServer.finish_request(self, request, client_address)

#------------------------------------------------
# Honeypot Request Handler
#------------------------------------------------

class HoneypotRequestHandler(BaseHTTPRequestHandler):

    def _write_json_response(self, status_code, payload, session=None):
        body = json.dumps(payload, indent=2, default=str).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        if session is not None:
            self.send_header("Set-Cookie", session_manager.build_cookie_header(session))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
            self.wfile.flush()

    def _handle_builtin_endpoint(self, req_path, req_method, session):
        if req_method not in {"GET", "HEAD"}:
            return False

        if req_path == "/health":
            self._write_json_response(
                200,
                {
                    "status": "healthy",
                    "service": "FirmPot",
                    "port": port,
                    "uptime_seconds": round(time.time() - server_start_time, 3),
                },
                session=session,
            )
            return True

        if req_path == "/ready":
            self._write_json_response(
                200,
                {
                    "ready": True,
                    "checks": {
                        "response_db": os.path.exists(db),
                        "word2vec_loaded": is_magnitude,
                        "mapping_loaded": len(mapping) > 0,
                    },
                },
                session=session,
            )
            return True

        if req_path == "/metrics":
            snapshot = metrics_tracker.get_metrics_snapshot()
            snapshot["session_stats"] = session_manager.get_stats()
            snapshot["detector_stats"] = attack_detector.get_stats()
            snapshot["log_stats"] = structured_logger.get_log_stats()
            self._write_json_response(200, snapshot, session=session)
            return True

        return False
    
    def send_response(self, code, message=None):
        self.log_request(code)
        self.send_response_only(code, message)
        self.error_message_format = "error"
        self.error_content_type = "text/plain"

    def handle_one_request(self):

        # Client IP addr and Port
        clientip = self.client_address[0]
        clientport = self.client_address[1]
        request_start = time.time()

        try:
            (r, w, e) = select.select([self.rfile], [], [], timeout)
            
            if len(r) == 0:
                errmsg = "Client({0}) data sending was too late.".format(clientip)
                raise socket.timeout(errmsg)
            else:
                self.raw_requestline = self.rfile.readline(65537) # read request

            # Request is None
            if not self.raw_requestline:
                self.close_connection = True
                return

            # Raw request line
            rrl = str(self.raw_requestline, 'iso-8859-1', errors='ignore')
            rrl = rrl.rstrip('\r\n')

            # Parse
            import re
            parse_request_flag = True
            if re.match("^[A-Z]", rrl) and (rrl.endswith("HTTP/1.0") or rrl.endswith("HTTP/1.1")):
                rrlmethod = rrl[:rrl.index(" ")]
                rrluri = rrl[rrl.index(" ")+1:rrl.rindex(" ")].replace(" ", "%20")
                rrluri = rrluri.replace("\"", "%22")
                rrlversion = rrl[rrl.rindex(" ")+1:]
                rrl2 = rrlmethod + " " + rrluri + " " + rrlversion
                self.raw_requestline = rrl2.encode()
            else:
                parse_request_flag = False

            # Parse failed
            if not self.parse_request() or not parse_request_flag:
                errmsg = "Client({0}) data cannot parse. {1}".format(clientip, str(self.raw_requestline))
                raise ValueError(errmsg)
            
            #------------------------------------
            # Parse a Request
            #------------------------------------
            
            # Request method
            req_method = self.requestline.split(' ')[0]

            # Request path 
            req_path = self.requestline.split(' ')[1].split('?')[0]

            # Request query
            if '?' in self.requestline:
                req_query = self.requestline.split(' ')[1].split('?')[1]
            else:
                req_query = "<EMP>"

            # Request body
            if 'content-length' in self.headers:
                content_len = int(self.headers['content-length'])
                if content_len > 0:
                    post_body = self.rfile.read(content_len)
                    req_body = post_body.decode()
                else:
                    req_body = "<EMP>"
            else:
                req_body = "<EMP>"
            
            #self.protocol_version = "HTTP/1.1"

            # Request list to input to the learinig model
            request_list = []
            request_list.append(req_method)
            request_list.append(req_path)
            request_list.append(req_query)
            request_list.append(req_body)
            
            # Request headers
            req_headers = ""
            for k, v in self.headers.items():
                req_headers += k + ": " + v + "@@@"
                if check_req_header(k):
                    request_list.append(get_shaped_header(k,v.replace(honeypot_ip, '')).replace(" ", "#"))
            req_headers = req_headers[:-3]
            user_agent = self.headers.get("User-Agent", "")
            session = session_manager.get_session(clientip, dict(self.headers))

            if self._handle_builtin_endpoint(req_path, req_method, session):
                metrics_tracker.record_request(
                    attack_tags=["normal"],
                    status_code=200,
                    response_time=time.time() - request_start,
                    client_ip=clientip,
                    path=req_path,
                    method=req_method,
                )
                structured_logger.log_event(
                    {
                        "src_ip": clientip,
                        "method": req_method,
                        "path": req_path,
                        "query": req_query if req_query != "<EMP>" else "",
                        "body": req_body if req_body != "<EMP>" else "",
                        "headers": dict(self.headers),
                        "status": 200,
                        "attack_tags": ["normal"],
                        "confidence": 1.0,
                        "rl_action_id": -1,
                        "profile": session.get("profile"),
                        "session_id": session.get("id"),
                    }
                )
                return

            attack_info = attack_detector.detect(
                method=req_method,
                path=req_path,
                query=req_query if req_query != "<EMP>" else "",
                body=req_body if req_body != "<EMP>" else "",
                headers=dict(self.headers),
                client_ip=clientip,
                user_agent=user_agent,
            )
 
            # Add <END>
            request_list.append("<END>")
            
            print("[*] Request List :", request_list)

            #------------------------------------
            # Predict Response_id 
            #------------------------------------

            k = 3
            context = rl_agent.build_state(
                req_method,
                req_path,
                attack_info["tags"],
                session.get("request_count", 0),
            )

            try:
                if is_magnitude:
                    idx_list, oov_list = string_to_int(request_list, is_magnitude=True)
                    print("[*] idx List :", idx_list)
                    if len(oov_list) == 0:
                        candidates = predict(idx_list, k=k)
                    else:
                        candidates = predict(idx_list, oov_list=oov_list, moov=moov, k=k)

                else:
                    idx_list, _ = string_to_int(request_list)
                    print("[*] idx List :", idx_list)
                    candidates = predict(idx_list, k=k)
            except Exception as e:
                logging_system(f"Prediction failed: {e}, falling back to default", True, False)
                candidates = [0]  # fallback

            try:
                res_id = rl_agent.select_response(context, candidates)
            except Exception as e:
                logging_system(f"RL selection failed: {e}, falling back to {candidates[0] if candidates else 0}", True, False)
                res_id = candidates[0] if candidates else 0

            #------------------------------------
            # Parse a Response
            #------------------------------------

            response_list = get_usable_response(c, res_id)
    
            res_status = response_list[0]
            res_headers = response_list[1]
            res_body = response_list[2]
    
            # Response status            
            self.send_response(res_status)
            self.send_header("Set-Cookie", session_manager.build_cookie_header(session))

            # Response body
            if res_body == "<EMP>":
                res_body = b''
            try:
                if "html" in res_body.decode('utf-8', errors='ignore'):
                    res_body = res_body.decode('utf-8')
                    res_body = replace_str(res_body, hardware_info)
                    res_body = res_body.encode()
            except:
                pass

            # Response headers
            for header in res_headers.split('@@@'):
                key = header.split(': ')[0]
                value = ': '.join(header.split(': ')[1:])

                if len(value) > 0:
                    if key.lower() == "Transfer-Encoding".lower() and "chunked" in value:
                        self.send_header("Content-Length", len(res_body))
                    elif key.lower() == "Content-Encoding".lower():
                        pass
                    else:
                        self.send_header(key, value)
                else:
                    if key.lower() == "Date".lower():
                        self.send_header(key, self.date_time_string())
                    elif key.lower() == "Content-Length".lower():
                        self.send_header(key, len(res_body))

            self.end_headers()
            
            # Response body
            if req_method != "HEAD":
                try:
                    self.wfile.write(res_body)
                except:
                    self.wfile.write(bytes(res_body))

            self.wfile.flush()

            # Update RL reward
            try:
                reward = 1.0 if "normal" not in attack_info["tags"] else 0.2
                rl_agent.update_reward(context, res_id, reward)
                metrics_tracker.record_rl_action(
                    context,
                    res_id,
                    reward,
                    rl_agent.get_q_value(context, res_id),
                )
                structured_logger.log_rl_decision(
                    context,
                    res_id,
                    reward,
                    rl_agent.get_q_value(context, res_id),
                )
            except Exception as e:
                logging_system(f"RL update failed: {e}", True, False)

            response_time = time.time() - request_start
            metrics_tracker.record_request(
                attack_tags=attack_info["tags"],
                status_code=res_status,
                response_time=response_time,
                client_ip=clientip,
                path=req_path,
                method=req_method,
                rl_action=res_id,
            )
            metrics_tracker.record_session(session["id"])

            session_manager.update_session(
                session,
                {"method": req_method, "path": req_path},
                attack_info,
                {"status": res_status, "rl_action": res_id},
            )
            session_snapshot = session_manager.get_session_metrics(session["id"])
            structured_logger.log_event(
                {
                    "src_ip": clientip,
                    "method": req_method,
                    "path": req_path,
                    "query": req_query if req_query != "<EMP>" else "",
                    "body": req_body if req_body != "<EMP>" else "",
                    "headers": dict(self.headers),
                    "status": res_status,
                    "attack_tags": attack_info["tags"],
                    "confidence": attack_info["confidence"],
                    "rl_action_id": res_id,
                    "profile": session.get("profile"),
                    "session_id": session.get("id"),
                    "session_duration_seconds": session_snapshot.get("duration_seconds", 0),
                    "session_request_count": session_snapshot.get("request_count", 0),
                    "response_time_ms": round(response_time * 1000, 2),
                }
            )

            if "normal" not in attack_info["tags"]:
                logging_system(
                    "Attack detected from {0}: tags={1} path={2}".format(
                        clientip, ",".join(attack_info["tags"]), req_path
                    ),
                    False,
                    False,
                )

            # Logging
            logging_access("{n}[{time}]{s}{clientip}{n}{method}{s}{path}{s}{query}{s}{body}{n}{headers}{n}{status_code}{s}{selected}{s}{candidates}{n}".format(
                                                                    time=get_time(),
                                                                    clientip=clientip,
                                                                    method=str(req_method),
                                                                    path=repr(req_path),
                                                                    query=repr(req_query),
                                                                    body=repr(req_body),
                                                                    headers=repr(req_headers),
                                                                    status_code=str(res_status),
                                                                    selected=str(res_id),
                                                                    candidates=str(candidates),
                                                                    s=' ',
                                                                    n='\n'
                                                                    ))            

        #----------------------------------------
        # Error
        #----------------------------------------
        
        except socket.timeout as e:
            emsg = "{0}".format(e)
            if emsg == "timed out":
                errmsg = "Session timed out. Client IP: {0}".format(clientip)
            else:
                errmsg = "Request timed out: {0}".format(emsg)
            self.log_error(errmsg)
            self.close_connection = True
            logging_system(errmsg, True, False)

        except Exception as e:
            errmsg = "Request handling Failed: {0} - {1}".format(type(e), e)
            self.close_connection = True
            logging_system(errmsg, True, False)
            return


def main():
    try:
        myServer = HoneypotHTTPServer((ip, port), HoneypotRequestHandler)
        myServer.timeout = timeout

        logger = logging.getLogger('SyslogLogger')
        logger.setLevel(logging.INFO)
        logging_system("Honeypot Start. {0}:{1} at {2}".format(ip, port, get_time()), False, False)
        myServer.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging_system(f"Server startup failed: {e}", True, True)

    try:
        myServer.server_close()
    except Exception:
        pass

#------------------------------------------------
# if __name__ == '__main__'
#------------------------------------------------

if __name__ == '__main__':

    # Define Arguments
    parser = argparse.ArgumentParser(description='Honeypot program')
    parser.add_argument('-m', '--magnitude', action='store_true', help='Use the Magnitude Mechanism to Respond.')
    parser.add_argument('-p', '--port', type=int, default=int(os.getenv('FIRMPOT_PORT', '8080')), help='Port to bind honeypot server (default: 8080).')
    args = parser.parse_args()

    port = args.port
    ensure_runtime_modules()
    
    # Logfile paths
    if not os.path.exists(common_paths["logs"]):
        os.makedirs(common_paths["logs"])
    accesslog = common_paths["logs"] + common_paths["access_log"]
    honeypotlog = common_paths["logs"] + common_paths["honeypot_log"]

    # Database
    db = common_paths["response_db"]
    conn = sqlite3.connect(db)
    c = conn.cursor()

    # Mapping dictionary
    mapping = {}
    try:
        c.execute('select * from mapping_table')
        for m in c.fetchall():
            mapping[m[1]] = m[0]
    except sqlite3.OperationalError:
        mapping = {"<PAD>": 0, "<END>": 1, "<EMP>": 2}

    # Get the max value of response_id
    c.execute('select max(res_id) from response_table')
    max_id = c.fetchall()[0][0]

    # Set the max index
    if max_id is None:
        train_params["max_index"] = max(len(mapping), 3)
    elif len(mapping) > max_id:
        train_params["max_index"] = len(mapping)
    else:
        train_params["max_index"] = max_id + 1

    # Flag of magnitude
    is_magnitude = args.magnitude
    if is_magnitude:
        word2vec_path = common_paths["word2vec"]
        if not os.path.exists(word2vec_path):
            print("[-] The word2vec path specified in the argument does not exist.")
            sys.exit(1)
        moov, encoder, decoder = get_model(word2vec_path)
    else:
        encoder, decoder = get_model()

    # RL Agent
    rl_agent = RLAgent()
    attack_detector = AttackDetector()
    structured_logger = StructuredLogger(common_paths["logs"], "access_structured.json", "access_structured.log")
    metrics_tracker = get_metrics()
    session_manager = SessionManager()
    server_start_time = time.time()

    main()
