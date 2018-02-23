#!/usr/bin/python

import json
from mf2py import Parser
import sys

if len(sys.argv) != 2:
    sys.exit( 'Usage: %s <url>' % sys.argv[0] )

url = sys.argv[1]

p = Parser( None, url, 'lxml' )
obj = p.to_dict()

print( json.dumps(obj, indent=4, sort_keys=True))
