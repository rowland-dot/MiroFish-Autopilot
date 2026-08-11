#!/usr/bin/env python3
"""MiroFish headless CLI — submit jobs, poll status, fetch reports.

Standard library only; no install step.

  export MIROFISH_ACCESS_CODE=...       # your Space access code
  python cli/mirofish.py submit --file report.docx --prompt "..."
  python cli/mirofish.py status <job_id>
  python cli/mirofish.py report <job_id> -o out.md
"""

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid

DEFAULT_URL = "https://leeroyy1288-mirofish.hf.space"


def parse_args(argv):
    p = argparse.ArgumentParser(prog="mirofish")
    p.add_argument("--url", default=os.environ.get("MIROFISH_URL", DEFAULT_URL))
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("submit", help="submit a new simulation job")
    s.add_argument("--file", required=True)
    s.add_argument("--prompt", required=True)

    t = sub.add_parser("status", help="poll a job's stage")
    t.add_argument("job_id")

    r = sub.add_parser("report", help="fetch a finished report")
    # job_id 在任务 done 后会被服务端清理（卡片被历史记录取代），
    # 所以同时支持用 status 里返回的 report_id 直取——那条路是稳定的
    r.add_argument("job_id", nargs="?")
    r.add_argument("--report-id", dest="report_id")
    r.add_argument("-o", "--output")

    d = sub.add_parser("delete", help="delete a job's card from the server")
    d.add_argument("job_id")

    return p.parse_args(argv)


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.cookie = None
        self._login()

    def _request(self, path, data=None, headers=None, method=None):
        req = urllib.request.Request(self.base + path, data=data, method=method)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        with urllib.request.urlopen(req, timeout=120) as resp:
            set_cookie = resp.headers.get("Set-Cookie")
            if set_cookie:
                self.cookie = set_cookie.split(";")[0]
            return resp.status, resp.read()

    def _login(self):
        code = os.environ.get("MIROFISH_ACCESS_CODE", "")
        if not code:
            return
        body = json.dumps({"code": code}).encode()
        try:
            self._request("/api/auth/login", body,
                          {"Content-Type": "application/json"})
        except urllib.error.HTTPError:
            pass          # 未开启口令门时登录会 404/405，忽略即可

    def get_json(self, path):
        try:
            status, raw = self._request(path)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        return status, json.loads(raw or b"{}")

    def get_raw(self, path):
        try:
            return self._request(path)
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def delete(self, path):
        try:
            return self._request(path, method="DELETE")
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post_file(self, path, file_path, fields):
        boundary = uuid.uuid4().hex
        name = os.path.basename(file_path)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        parts = []
        for k, v in fields.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="{k}"\r\n\r\n{v}\r\n'.encode())
        with open(file_path, "rb") as f:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="file"; filename="{name}"\r\n'
                         f"Content-Type: {ctype}\r\n\r\n".encode()
                         + f.read() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        try:
            status, raw = self._request(
                path, body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        return status, json.loads(raw or b"{}")


def main(argv=None):
    ns = parse_args(argv if argv is not None else sys.argv[1:])
    c = Client(ns.url)

    if ns.command == "submit":
        status, body = c.post_file("/api/jobs", ns.file, {"prompt": ns.prompt})
        print(json.dumps(body.get("data", body), ensure_ascii=False))
        return 0 if status == 200 else 1

    if ns.command == "status":
        status, body = c.get_json(f"/api/jobs/{ns.job_id}")
        print(json.dumps(body.get("data", body), ensure_ascii=False))
        return 0 if status == 200 else 1

    if ns.command == "delete":
        status, raw = c.delete(f"/api/pipeline/{ns.job_id}")
        print(json.dumps({"job_id": ns.job_id, "deleted": status == 200},
                         ensure_ascii=False))
        return 0 if status == 200 else 1

    if ns.report_id:
        # 直取报告：绕开已被清理的任务卡片
        status, raw = c.get_raw(f"/api/report/{ns.report_id}/download?format=md")
    elif ns.job_id:
        status, raw = c.get_raw(f"/api/jobs/{ns.job_id}/report")
    else:
        print(json.dumps({"error": "report needs a job_id or --report-id"}))
        return 2
    if status != 200:
        print(raw.decode("utf-8", "replace"))
        return 1
    if ns.output:
        with open(ns.output, "wb") as f:
            f.write(raw)
        print(f"saved {ns.output} ({len(raw)} bytes)")
    else:
        sys.stdout.write(raw.decode("utf-8", "replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
