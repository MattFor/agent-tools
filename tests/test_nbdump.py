import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'nbdump')
PNG = base64.b64encode(b'\x89PNG' + b'\0' * 4096).decode()
NB = {
	'nbformat': 4,
	'nbformat_minor': 5,
	'metadata': {},
	'cells': [
		{'cell_type': 'markdown', 'metadata': {}, 'source': ['# Title\n', 'text']},
		{
			'cell_type': 'code',
			'execution_count': 1,
			'metadata': {},
			'source': ['print("hi")\n', 'for i in range(3): print(i, end="\\r")'],
			'outputs': [
				{'output_type': 'stream', 'name': 'stdout', 'text': ['hi\n', '0\r1\r2\n']},
				{'output_type': 'execute_result', 'execution_count': 1, 'metadata': {}, 'data': {'text/plain': '42'}},
			],
		},
		{
			'cell_type': 'code',
			'execution_count': 2,
			'metadata': {},
			'source': '1 / 0',
			'outputs': [
				{
					'output_type': 'error',
					'ename': 'ZeroDivisionError',
					'evalue': 'division by zero',
					'traceback': ['\x1b[0;31m---------\x1b[0m', '\x1b[0;32mCell In[2], line 1\x1b[0m\n----> 1 1 / 0'],
				}
			],
		},
		{
			'cell_type': 'code',
			'execution_count': None,
			'metadata': {},
			'source': 'plot()',
			'outputs': [
				{
					'output_type': 'display_data',
					'metadata': {},
					'data': {'image/png': PNG, 'text/plain': '<Figure size 640x480 with 1 Axes>'},
				},
				{'output_type': 'stream', 'name': 'stderr', 'text': 'x' * 500},
			],
		},
	],
}


class Nbdump(unittest.TestCase):
	def setUp(self):
		fd, self.path = tempfile.mkstemp(suffix='.ipynb')
		with os.fdopen(fd, 'w') as f:
			json.dump(NB, f)

	def run_nbdump(self, *args):
		return subprocess.run([sys.executable, BIN, self.path, *args], check=False, capture_output=True, text=True)

	def test_all_cells(self):
		r = self.run_nbdump()
		self.assertEqual(r.returncode, 0, r.stderr)
		self.assertIn('=== [0] markdown\n# Title\ntext\n=== [1] code exec=1\nprint("hi")', r.stdout)
		self.assertIn('--- stdout\nhi\n2\n--- result\n42\n', r.stdout)
		self.assertIn('--- error\nZeroDivisionError: division by zero\n---------\nCell In[2], line 1', r.stdout)
		self.assertNotIn('\x1b', r.stdout)
		self.assertIn('=== [3] code exec=-', r.stdout)
		self.assertIn('--- display\n[image/png 4 KB]\n<Figure size 640x480 with 1 Axes>', r.stdout)

	def test_select_and_parts(self):
		r = self.run_nbdump('1,3', '--src')
		self.assertNotIn('[0]', r.stdout)
		self.assertNotIn('[2]', r.stdout)
		self.assertNotIn('---', r.stdout)
		self.assertIn('plot()', r.stdout)
		r = self.run_nbdump('0-2', '--out')
		self.assertNotIn('markdown', r.stdout)
		self.assertIn('exec=2\n--- error', r.stdout)
		self.assertIn('ZeroDivisionError', r.stdout)
		self.assertNotEqual(self.run_nbdump('9').returncode, 0)

	def test_errors_only(self):
		r = self.run_nbdump('--errors')
		lines = r.stdout.splitlines()
		self.assertTrue(lines[0].endswith('4 cells, 3 code, 2 executed, 1 with errors'), lines[0])
		self.assertEqual(lines[1], '=== [2] code exec=2')
		self.assertNotIn('[1]', r.stdout)

	def test_cap(self):
		r = self.run_nbdump('3', '-t', '100')
		self.assertIn('x' * 50 + '\n… [400 chars cut] …\n' + 'x' * 50 + '\n', r.stdout)


if __name__ == '__main__':
	unittest.main()
