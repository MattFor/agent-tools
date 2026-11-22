import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'claude-usage')
IN_2H = time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime(time.time() + 2 * 3600 + 30))
OLD = {
	'five_hour': {'utilization': 42.5, 'resets_at': IN_2H},
	'seven_day': {'utilization': 80, 'resets_at': None},
	'seven_day_opus': {'utilization': 10, 'resets_at': IN_2H},
	'extra_usage': {'is_enabled': False},
}
NEW = {'limits': [{'group': 'session', 'percent': 5, 'resets_at': IN_2H}, {'group': 'weekly', 'percent': 90}]}


class Usage(unittest.TestCase):
	def setUp(self):
		self.hits = []
		self.reply = (200, {}, OLD)
		outer = self

		class H(http.server.BaseHTTPRequestHandler):
			def do_GET(self):
				outer.hits.append((self.headers.get('Authorization'), self.headers.get('anthropic-beta')))
				code, headers, body = outer.reply
				self.send_response(code)
				for k, v in headers.items():
					self.send_header(k, v)
				self.end_headers()
				self.wfile.write(json.dumps(body).encode())

			def log_message(self, format, *args):
				pass

		self.srv = http.server.HTTPServer(('127.0.0.1', 0), H)
		threading.Thread(target=self.srv.serve_forever, daemon=True).start()
		self.addCleanup(self.srv.server_close)
		self.addCleanup(self.srv.shutdown)
		self.home = tempfile.mkdtemp()
		self.creds(True)

	def creds(self, ok):
		if ok:
			with open(os.path.join(self.home, '.credentials.json'), 'w') as f:
				json.dump({'claudeAiOauth': {'accessToken': 'sekrit'}}, f)

	def env(self, port=None):
		return {
			**os.environ,
			'CLAUDE_CONFIG_DIR': self.home,
			'CLAUDE_USAGE_URL': f'http://127.0.0.1:{port or self.srv.server_port}/u',
		}

	def run_usage(self, *args, **kw):
		return subprocess.run(
			[sys.executable, BIN, *args], check=False, capture_output=True, text=True, env=self.env(**kw)
		)

	def test_lines_and_token_never_printed(self):
		r = self.run_usage()
		self.assertEqual(r.returncode, 0, r.stderr)
		rows = r.stdout.splitlines()
		self.assertEqual(
			[x.split()[:3] for x in rows], [['5h', '42.5%', 'resets'], ['7d', '80%', 'resets'], ['7d', 'opus', '10%']]
		)
		self.assertIn('(in 2h 0m)', rows[0])
		self.assertIn('resets -', rows[1])
		self.assertEqual(self.hits[0], ('Bearer sekrit', 'oauth-2025-04-20'))
		self.assertNotIn('sekrit', r.stdout + r.stderr)

	def test_new_shape_and_json(self):
		self.reply = (200, {}, NEW)
		self.assertEqual([x.split()[0] for x in self.run_usage().stdout.splitlines()], ['5h', '7d'])
		self.assertEqual(json.loads(self.run_usage('--json').stdout), NEW)

	def test_fail_above(self):
		self.assertEqual(self.run_usage('--fail-above', '80').returncode, 1)
		self.assertEqual(self.run_usage('--fail-above', '81').returncode, 0)

	def test_errors(self):
		self.reply = (401, {}, {})
		r = self.run_usage()
		self.assertEqual(r.returncode, 2)
		self.assertIn('login expired', r.stderr)
		self.reply = (429, {'Retry-After': '7'}, {'error': {'type': 'rate_limit_error'}})
		r = self.run_usage()
		self.assertEqual(r.returncode, 4)
		self.assertIn('rate limited, try again later (retry after 7s)', r.stderr)
		self.reply = (500, {}, {})
		self.assertEqual(self.run_usage().returncode, 3)
		self.assertEqual(self.run_usage(port=1).returncode, 3)
		os.remove(os.path.join(self.home, '.credentials.json'))
		r = self.run_usage()
		self.assertEqual(r.returncode, 2)
		self.assertIn('no Claude login', r.stderr)

	def test_watch_never_polls_faster_than_300s(self):
		p = subprocess.Popen(
			[sys.executable, BIN, '--watch', '1'],
			env=self.env(),
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
		)
		self.addCleanup(p.wait)
		self.addCleanup(p.kill)
		self.assertTrue((p.stdout.readline() if p.stdout else '').startswith('5h'))
		time.sleep(2.5)
		self.assertEqual(len(self.hits), 1)
		p.kill()
		self.assertIn('raised to 300s', p.stderr.read() if p.stderr else '')


if __name__ == '__main__':
	unittest.main()
