#!/usr/bin/python

import argparse
import json
from mf2py import Parser
import sys

parser = argparse.ArgumentParser(description='Emit JSON that contains the recognized microformats in an HTML page')
parser.add_argument('--stdin', action='store_true', help='If provided, read from standard input')
parser.add_argument('url', nargs='*', help='If not reading from stdin, read from this URL')

args = parser.parse_args()

content=None

if args.stdin:
  if args.url:
    sys.exit('ERROR: Either give --stdin or <url>, not both' )
  content = sys.stdin.read()
else:
  if len(args.url) != 1:
    sys.exit('ERROR: Must provide a URL or --stdin')

p = Parser( content, None if len(args.url) == 0 else args.url[0], 'lxml' )
obj = p.to_dict()

print( json.dumps(obj, indent=4, sort_keys=True))
