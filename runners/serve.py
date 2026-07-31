#!/usr/bin/env python3
"""Multi-threaded Range-enabled HTTP server for testing OSWM PMTiles locally."""

import http.server
import io
import os
import sys

class RangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length, Accept-Ranges")
        super().end_headers()

    def send_head(self):
        if "Range" not in self.headers:
            self.send_header("Accept-Ranges", "bytes")
            return super().send_head()

        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            return super().send_head()

        size = os.path.getsize(path)
        range_header = self.headers["Range"]
        try:
            bytes_range = range_header.split("=")[1]
            start_str, end_str = bytes_range.split("-")
            start = int(start_str)
            end = int(end_str) if end_str else size - 1
        except Exception:
            return super().send_head()

        if start >= size or end >= size or start > end:
            self.send_error(416, "Requested Range Not Satisfiable")
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        try:
            f = open(path, "rb")
            f.seek(start)
            data = f.read(length)
            f.close()
            return io.BytesIO(data)
        except IOError:
            self.send_error(404, "File not found")
            return None

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server_address = ("0.0.0.0", port)
    httpd = http.server.ThreadingHTTPServer(server_address, RangeHTTPRequestHandler)
    print(f"Serving HTTP on 0.0.0.0 port {port} (http://localhost:{port}/) ...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    main()
