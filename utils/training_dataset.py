import glob
import json
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from utils.http_headers import shape_req_headers


FuzzSample = Dict[str, object]
TrainingRequest = Tuple[str, str, str, str, str]
TrainingResponse = Tuple[int]


def _normalize_text(value, empty_token: str = "<EMP>") -> str:
    if value is None:
        return empty_token
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    value = str(value).strip()
    return value if value else empty_token


def _normalize_headers(headers) -> str:
    if headers in (None, "", "<EMP>"):
        return "<EMP>"
    if isinstance(headers, str):
        return headers.replace(" ", "#") if headers else "<EMP>"
    if isinstance(headers, dict):
        normalized = {
            "-".join(part.capitalize() for part in str(key).split("-")): str(value)
            for key, value in headers.items()
        }
        shaped = shape_req_headers(normalized)
        if not shaped:
            shaped = "@@@".join(
                f"{key}: {value}" for key, value in normalized.items()
            )
        return shaped if shaped else "<EMP>"
    return _normalize_text(headers).replace(" ", "#")


def normalize_training_row(
    method,
    path,
    query,
    headers,
    body,
    res_id,
    source: str = "unknown",
    attack_tags: Optional[Sequence[str]] = None,
) -> FuzzSample:
    return {
        "method": _normalize_text(method, "GET"),
        "path": _normalize_text(path, "/"),
        "query": _normalize_text(query),
        "headers": _normalize_headers(headers),
        "body": _normalize_text(body).replace(" ", "#"),
        "res_id": int(res_id),
        "source": source,
        "attack_tags": list(attack_tags or []),
    }


def dataset_to_training_pairs(samples: Iterable[FuzzSample]) -> Tuple[List[TrainingRequest], List[TrainingResponse]]:
    requests: List[TrainingRequest] = []
    responses: List[TrainingResponse] = []

    for sample in samples:
        requests.append(
            (
                sample["method"],
                sample["path"],
                sample["query"],
                sample["headers"],
                sample["body"],
            )
        )
        responses.append((int(sample["res_id"]),))

    return requests, responses


def save_samples(dataset_path: str, samples: Sequence[FuzzSample]) -> None:
    os.makedirs(os.path.dirname(dataset_path), exist_ok=True)
    payload = {
        "version": 1,
        "sample_count": len(samples),
        "samples": list(samples),
    }
    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_samples(dataset_path: str) -> List[FuzzSample]:
    with open(dataset_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, dict) and "samples" in payload:
        return list(payload["samples"])
    if isinstance(payload, list):
        return payload
    return []


def export_sqlite_training_set(db_path: str) -> List[FuzzSample]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("select req_method, req_path, req_query, req_headers, req_body, res_id from learning_table")
    rows = c.fetchall()
    conn.close()

    return [
        normalize_training_row(*row, source="fuzz")
        for row in rows
    ]


def collect_attack_tokens(method: str, path: str, query: str, body: str, headers: Dict, attack_tags: Sequence[str]) -> List[str]:
    tokens = []
    for part in [method, path, query, body]:
        text = _normalize_text(part, "")
        if text:
            tokens.extend(re.findall(r"[A-Za-z0-9_./%-]+", text))
    for key, value in (headers or {}).items():
        tokens.extend(re.findall(r"[A-Za-z0-9_./%-]+", f"{key}:{value}"))
    tokens.extend(attack_tags or [])
    return tokens


def load_attack_log_samples(log_dir: str, default_res_id: int = 0) -> List[FuzzSample]:
    samples: List[FuzzSample] = []
    if not log_dir or not os.path.isdir(log_dir):
        return samples

    samples.extend(_load_structured_json_samples(log_dir, default_res_id))
    samples.extend(_load_text_log_samples(log_dir, default_res_id))

    deduped: List[FuzzSample] = []
    seen = set()
    for sample in samples:
        key = (
            sample["method"],
            sample["path"],
            sample["query"],
            sample["headers"],
            sample["body"],
            sample["res_id"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sample)
    return deduped


def _load_structured_json_samples(log_dir: str, default_res_id: int) -> List[FuzzSample]:
    samples: List[FuzzSample] = []
    jsonl_path = os.path.join(log_dir, "access_structured.json")
    if not os.path.exists(jsonl_path):
        return samples

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            attack_tags = event.get("attack_tags") or []
            if not attack_tags:
                attack_tags = ["normal"]
            samples.append(
                normalize_training_row(
                    event.get("method", "GET"),
                    event.get("path", "/"),
                    event.get("query", "<EMP>"),
                    event.get("headers", {}),
                    event.get("body", "<EMP>"),
                    default_res_id,
                    source="honeypot_logs",
                    attack_tags=attack_tags,
                )
            )

    return samples


def _load_text_log_samples(log_dir: str, default_res_id: int) -> List[FuzzSample]:
    samples: List[FuzzSample] = []
    line_pattern = re.compile(
        r"\[(?P<timestamp>[^\]]+)\]\s+(?P<src_ip>\S+)\s+\S+\s+"
        r"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+->\s+(?P<status>\d+)\s+\|\s+"
        r"Attack:\s+(?P<tags>[^|]+)"
    )

    for log_path in glob.glob(os.path.join(log_dir, "*.log")):
        if os.path.basename(log_path) == "honeypot.log":
            continue
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                match = line_pattern.search(line)
                if not match:
                    continue

                path_with_query = match.group("path")
                if "?" in path_with_query:
                    path, query = path_with_query.split("?", 1)
                else:
                    path, query = path_with_query, "<EMP>"

                tags_chunk = match.group("tags").split("(")[0].strip()
                attack_tags = [tag.strip() for tag in tags_chunk.split(",") if tag.strip()]
                if not attack_tags:
                    attack_tags = ["normal"]

                samples.append(
                    normalize_training_row(
                        match.group("method"),
                        path,
                        query,
                        "<EMP>",
                        "<EMP>",
                        default_res_id,
                        source="honeypot_logs",
                        attack_tags=attack_tags,
                    )
                )
    return samples
