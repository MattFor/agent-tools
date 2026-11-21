import os
import shutil
import subprocess
import sys
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'tui')


@unittest.skipUnless(shutil.which('tmux'), 'tmux not installed')
class Tui(unittest.TestCase):
	def setUp(self):
		self.name = f'test{os.getpid()}'

	def tearDown(self):
		self.run_tui('stop', self.name)

	def run_tui(self, *args, env=None):
		return subprocess.run(
			[sys.executable, BIN, *args], check=False, capture_output=True, text=True, env=env or os.environ
		)

	def test_session(self):
		env = dict(os.environ, TUI_PULSE_SINK='null_test')
		cmd = 'echo sink=$PULSE_SINK; read x; echo "got $x";'
		r = self.run_tui('start', self.name, '-s', '60x10', '--', 'sh', '-c', cmd, env=env)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn('sink=null_test', self.run_tui('wait', self.name, 'sink=').stdout)
		r = self.run_tui('type', self.name, 'a;b -x')
		self.assertIn('a;b -x', r.stdout)
		self.run_tui('keys', self.name, 'Enter')
		r = self.run_tui('wait', self.name, r'^\[exited 0\]', '-t', '5')
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn('got a;b -x', r.stdout)
		self.assertFalse(r.stdout.endswith('\n\n'))
		self.assertEqual(self.run_tui('screen', self.name, '--lines', '3-3').stdout, 'got a;b -x\n')
		r = self.run_tui('wait', self.name, 'never there', '-t', '0.4')
		self.assertEqual(r.returncode, 124)
		self.assertIn('[exited 0]', r.stdout)
		self.assertEqual(self.run_tui('stop', self.name).stdout, f'stopped {self.name}\n')
		r = self.run_tui('screen', self.name)
		self.assertNotEqual(r.returncode, 0)
		self.assertIn('no session', r.stderr)

	def test_ctrl_c_and_single_string_command(self):
		self.run_tui('start', self.name, '--', 'echo ready; sleep 30')
		self.run_tui('wait', self.name, 'ready')
		self.run_tui('keys', self.name, '-d', '0.2', 'C-c')
		r = self.run_tui('wait', self.name, r'\[exited 130\]', '-t', '5')
		self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
	unittest.main()
