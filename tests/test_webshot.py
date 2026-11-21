import functools
import http.server
import json
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'webshot')
PAGE = """<!doctype html><title>t</title>
<script>console.error('boom from page')</script>
<input id="i" value="old"><button id="b" onclick="this.textContent = 'clicked'">click me</button>
<div style="height: 2000px"></div>
"""


class Quiet(http.server.SimpleHTTPRequestHandler):
	def log_message(self, *args):
		pass


def png_size(path):
	with open(path, 'rb') as f:
		head = f.read(24)
	assert head[:8] == b'\x89PNG\r\n\x1a\n', head[:8]
	return struct.unpack('>II', head[16:24])


class Webshot(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if not shutil.which('node'):
			raise unittest.SkipTest('node not found')
		cls.d = tempfile.mkdtemp()
		with open(os.path.join(cls.d, 'index.html'), 'w') as f:
			f.write(PAGE)
		cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=cls.d))
		threading.Thread(target=cls.server.serve_forever, daemon=True).start()
		cls.url = f'http://127.0.0.1:{cls.server.server_address[1]}/'
		probe = cls.run_webshot(cls.url)
		if 'no browser found' in probe.stderr or 'needs Node' in probe.stderr:
			cls.tearDownClass()
			raise unittest.SkipTest(probe.stderr.strip())

	@classmethod
	def tearDownClass(cls):
		cls.server.shutdown()
		cls.server.server_close()
		shutil.rmtree(cls.d)

	@staticmethod
	def run_webshot(*args):
		return subprocess.run(['node', BIN, *args], check=False, capture_output=True, text=True, timeout=60)

	def test_screenshot_and_report(self):
		out = os.path.join(self.d, 'shot.png')
		r = self.run_webshot(self.url, out, '--size', '800x600')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual(png_size(out), (800, 600))
		self.assertIn(f'url: {self.url}\n', r.stderr)
		self.assertIn('status: 200\n', r.stderr)
		self.assertIn('console error: boom from page', r.stderr)

	def test_mobile_full(self):
		out = os.path.join(self.d, 'full.png')
		r = self.run_webshot(self.url, out, '--mobile', '--full')
		self.assertEqual(r.returncode, 0, r.stderr)
		width, height = png_size(out)
		self.assertGreaterEqual(height, 2000 * 3)
		self.assertEqual(width % 3, 0)

	def test_eval(self):
		r = self.run_webshot(
			self.url, '--dark', '--eval', "[document.title, matchMedia('(prefers-color-scheme: dark)').matches]"
		)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual(json.loads(r.stdout), ['t', True])

	def test_click_and_type(self):
		r = self.run_webshot(self.url, '--type', '#i', 'new', '--click', '#b', '--eval', '[b.textContent, i.value]')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertEqual(json.loads(r.stdout), ['clicked', 'new'])

	def test_failures(self):
		r = self.run_webshot(self.url + 'missing')
		self.assertEqual(r.returncode, 1, r.stderr)
		self.assertIn('status: 404', r.stderr)
		r = self.run_webshot(self.url, '--click', '#nope')
		self.assertEqual(r.returncode, 3)
		self.assertIn('no element matches', r.stderr)
		r = self.run_webshot(self.url, '--wait-for', '.never', '--timeout', '1')
		self.assertEqual(r.returncode, 3)
		self.assertIn('timed out', r.stderr)
		self.assertEqual(self.run_webshot('--size').returncode, 2)


if __name__ == '__main__':
	unittest.main()
