import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'xlab')
TOOLS = ('Xvfb', 'xdotool', 'xwininfo', 'import', 'magick')
# App args, and a key that makes it exit once focused.
APPS = {'xmessage': (['-default', 'okay', 'xlab test'], 'Return'), 'xterm': (['-e', 'sleep', '60'], 'ctrl+c')}
APP = next((a for a in APPS if shutil.which(a)), None)


def xlab(*args):
	return subprocess.run([sys.executable, BIN, *args], check=False, capture_output=True, text=True)


def xvfb_running(disp):
	for pid in filter(str.isdigit, os.listdir('/proc')):
		try:
			with open(f'/proc/{pid}/cmdline', 'rb') as f:
				args = f.read().split(b'\0')
		except OSError:
			continue
		if os.path.basename(args[0]) == b'Xvfb' and disp.encode() in args:
			return True
	return False


class Refusals(unittest.TestCase):
	def test_no_input_on_real_display(self):
		r = xlab('input', '-d', ':0', 'click', '1', '1')
		self.assertEqual(r.returncode, 1)
		self.assertIn('refusing', r.stderr)

	def test_bad_step(self):
		r = xlab('input', '-d', ':99', 'click', '1')
		self.assertEqual(r.returncode, 2)


@unittest.skipUnless(all(map(shutil.which, TOOLS)) and APP, f'needs {", ".join(TOOLS)} and xmessage or xterm')
class EndToEnd(unittest.TestCase):
	def test_up_win_input_shot_down(self):
		r = xlab('up', '640x480')
		self.assertEqual(r.returncode, 0, r.stderr)
		env = dict(os.environ)
		for line in r.stdout.splitlines():
			k, v = line.removeprefix('export ').split('=', 1)
			env[k] = v
		disp = env['DISPLAY']
		self.addCleanup(xlab, 'down', disp)
		self.assertGreaterEqual(int(disp[1:]), 90)
		self.assertTrue(xvfb_running(disp))

		assert APP is not None  # the class is skipped without one
		args, quit_key = APPS[APP]
		app = subprocess.Popen([APP, '-title', 'xlab-test', *args], env=env, stderr=subprocess.DEVNULL)
		self.addCleanup(app.kill)
		r = xlab('-d', disp, 'win', 'xlab-test', '-t', '10')
		self.assertEqual(r.returncode, 0, r.stderr)
		wid, geom, title = r.stdout.split(maxsplit=2)
		self.assertEqual(title.strip(), 'xlab-test')
		m = re.fullmatch(r'\d+x\d+([+-]\d+)([+-]\d+)', geom)
		assert m, geom
		x, y = map(int, m.groups())

		r = xlab('input', '-d', disp, '-w', wid, 'click', '5', '6')
		self.assertEqual(r.returncode, 0, r.stderr)
		loc = subprocess.run(
			['xdotool', 'getmouselocation', '--shell'], check=False, env=env, capture_output=True, text=True
		).stdout
		self.assertIn(f'X={x + 5}\nY={y + 6}\n', loc)

		png = os.path.join(self.enterContext(tempfile.TemporaryDirectory()), 's.png')
		r = xlab('shot', '-d', disp, '-w', 'xlab-test', '--crop', '30x20+1+2', png)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn(' 30x20 ', r.stdout)
		with open(png, 'rb') as f:
			head = f.read(24)
		self.assertEqual(head[:8], b'\x89PNG\r\n\x1a\n')
		self.assertEqual(struct.unpack('>II', head[16:24]), (30, 20))

		r = xlab('input', '-d', disp, '-w', wid, 'focus', 'key', quit_key)
		self.assertEqual(r.returncode, 0, r.stderr)
		app.wait(5)

		self.assertEqual(xlab('-d', disp, 'win', 'xlab-test', '-t', '0.3').returncode, 124)
		r = xlab('down', disp)
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertFalse(xvfb_running(disp))


if __name__ == '__main__':
	unittest.main()
