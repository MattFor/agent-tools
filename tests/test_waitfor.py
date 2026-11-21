import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'waitfor')


def later(delay, fn, *args):
	t = threading.Timer(delay, fn, args)
	t.start()
	return t


def write(path, text, mode='w'):
	with open(path, mode) as f:
		f.write(text)


class Waitfor(unittest.TestCase):
	def setUp(self):
		self.d = tempfile.mkdtemp()

	def run_waitfor(self, *args):
		return subprocess.run([sys.executable, BIN, *args], check=False, capture_output=True, text=True)

	def test_http_and_port_after_delay(self):
		with socket.socket() as s:
			s.bind(('127.0.0.1', 0))
			port = s.getsockname()[1]
		code = 'import time, http.server as h; time.sleep(0.8); '
		code += f'h.test(h.SimpleHTTPRequestHandler, port={port}, bind="127.0.0.1")'
		srv = subprocess.Popen(
			[sys.executable, '-c', code], cwd=self.d, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
		)
		try:
			url = f'http://127.0.0.1:{port}/missing'
			r = self.run_waitfor('-t', '10', '-i', '0.2', 'http', url)
			self.assertEqual(r.returncode, 0, r.stderr)
			self.assertIn('answered 404', r.stdout)
			self.assertEqual(self.run_waitfor('-t', '5', 'http', url, '404').returncode, 0)
			r = self.run_waitfor('-t', '5', 'port', str(port))
			self.assertEqual(r.returncode, 0, r.stderr)
			self.assertIn(f'127.0.0.1:{port} is open', r.stdout)
			r = self.run_waitfor('-t', '0.5', 'http', url, '200')
			self.assertEqual(r.returncode, 124)
			self.assertIn('answered 404', r.stderr)
		finally:
			srv.kill()
			srv.wait()

	def test_file_and_command(self):
		p = os.path.join(self.d, 'out')
		later(0.4, write, p, '')
		t = later(0.8, write, p, 'x')
		r = self.run_waitfor('-t', '5', '-i', '0.1', 'file', p)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn('has 1 bytes', r.stdout)
		t.join()
		q = os.path.join(self.d, 'flag')
		later(0.4, write, q, 'y')
		r = self.run_waitfor('-t', '5', '-i', '0.1', '--', 'sh', '-c', f'test -s {q}')
		self.assertEqual(r.returncode, 0, r.stderr)

	def test_log(self):
		p = os.path.join(self.d, 'log')
		write(p, 'starting\nready on 8080\n')
		r = self.run_waitfor('-t', '2', 'log', p, r'ready on \d+')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn('ready on 8080', r.stdout)
		later(0.4, write, p, 'still going\nERROR boom\n', 'a')
		r = self.run_waitfor('-t', '5', '-i', '0.1', 'log', p, '^ERROR')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn('ERROR boom', r.stdout)

	def test_timeout(self):
		r = self.run_waitfor('-t', '0.5', 'file', os.path.join(self.d, 'never'))
		self.assertEqual(r.returncode, 124)
		self.assertIn('does not exist', r.stderr)
		self.assertEqual(len(r.stderr.splitlines()), 1)

	def test_proc_never_matches_itself_and_gone(self):
		tag = f'waitfor-tag-{os.getpid()}'
		self.assertEqual(self.run_waitfor('-t', '0.5', 'proc', tag).returncode, 124)
		p = subprocess.Popen(['sh', '-c', 'sleep 0.8', tag])
		try:
			r = self.run_waitfor('-t', '5', 'proc', tag)
			self.assertEqual(r.returncode, 0, r.stderr)
			# Left unreaped on purpose: a zombie counts as gone.
			r = self.run_waitfor('-t', '5', '-i', '0.1', 'gone', str(p.pid))
			self.assertEqual(r.returncode, 0, r.stderr)
			self.assertIn('is gone', r.stdout)
		finally:
			p.kill()
			p.wait()
		self.assertEqual(self.run_waitfor('-t', '5', 'gone', tag).returncode, 0)


if __name__ == '__main__':
	unittest.main()
