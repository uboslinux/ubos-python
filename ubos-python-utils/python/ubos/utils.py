#!/usr/bin/python
#
# Collection of utility functions.
#
# Copyright (C) 2014 and later, Indie Computing Corp. All rights reserved. License: see package.
#

import calendar
import json
import os
import pkgutil
import re
import subprocess
import time
import ubos.logging

def findSubmodules(package) :
    """
    Find all submodules in the named package

    package: the package
    return: array of module names
    """
    ret = []
    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        ret.append(modname)
    return ret


def myexec(cmd,stdin=None, captureStdout=False, captureStderr=False):
    """
    Wrapper around executing sub-commands, so we can log what is happening.

    cmd: the command to be executed by the shell
    stdin: content to be piped into the command, if any
    captureStdout: if true, capture the commands stdout and return
    captureStderr: if true, capture the commands stderr and return
    return: if no capture: return code; otherwise tuple
    """
    if stdin :
        try :
            # make sure we have a bytes-like object
            stdin = stdin.encode()
        except:
            pass

    if stdin is None:
        ubos.logging.debugAndSuspend('myexec:', cmd)
    else:
        ubos.logging.debugAndSuspend('myexec:', cmd, 'with stdin:', stdin)

    ubos.logging.trace(cmd, 'None' if stdin==None else ( "with stdin of length %d " % len(stdin)))

    ret = subprocess.run(
            cmd,
            shell  = True,
            input  = stdin,
            stdout = subprocess.PIPE if captureStdout else None,
            stderr = subprocess.PIPE if captureStderr else None)

    if captureStdout or captureStderr:
        return (ret.returncode,
                ret.stdout if hasattr(ret, 'stdout') else None,
                ret.stderr if hasattr(ret, 'stderr') else None )
    else:
        return ret.returncode


def slurpFile( fileName ) :
    """
    Slurp the content of a file

    fileName: the name of the file to read
    return: the content of the file
    """
    ubos.logging.trace( 'slurpFile', fileName )

    try :
        with open(fileName, 'r') as fd:
            ret = fd.read()

        return ret

    except :
        ubos.logging.error( 'Cannot read file', fileName );
        return None


def readJsonFromFile( fileName, msg = None ):
    """
    Read and parse JSON from a file. In addition, accept # for comments.

    fileName: the JSON file to read
    msg: if an error occurs, use this error message
    return: the parsed JSON
    """
    ubos.logging.trace( fileName )

    try :
        with open(fileName, 'r') as fd:
            jsonContent = fd.read()

        jsonContent = re.sub(r'(?<!\\)#.*', '', jsonContent)
        ret         = json.loads(jsonContent)
        return ret

    except:
        if msg :
            ubos.logging.error( msg )
        else :
            ubos.logging.error( "JSON parsing error in file: %s" % fileName )

        return None


def readJsonFromString( s, msg = None ) :
    """
    Read and parse JSON from String

    string: the JSON string
    msg: if an error occurs, use this error message
    return: JSON object
    """

    try:
        ret = json.loads(s)
        return ret

    except:
        if msg :
            ubos.logging.error( msg )
        else :
            ubos.logging.error( 'JSON parsing error' )

    return None


def writeJsonToFile(fileName, j, mode=None ) :
    """
    Write JSON to a file.

    fileName: name of the file to write
    j: the JSON object to write
    mode: the file permissions to set; default is: umask
    """
    with open(fileName, 'w') as fd:
        json.dump(j, fd, indent=4, sort_keys=True)

    if mode != None:
        os.chmod(fileName, mode)


def writeJsonToStdout(j) :
    """
    Write JSON to stdout.

    j: the JSON object to write
    """
    print(json.dumps(j, indent=4, sort_keys=True))


def writeJsonToString(j) :
    """
    Write JSON to a string

    j: the JSON object to write
    return: the string
    """
    return json.dumps(j, indent=4, sort_keys=True)


def saveFile(fileName, content, mode=None) :
    """
    Save content to a file.

    fileName: name of the file to write
    content: the content to write
    mode: the file permissions to set; default is: umask
    """
    with open(fileName, 'w') as fd:
        fd.write(content)

    if mode != None:
        os.chmod(fileName, mode)


def time2string(t):
    """
    Format time consistently

    t: the time to be formatted
    return: formatted time
    """
    ts  = time.gmtime(t)
    ret = time.strftime('%Y%m%d-%H%M%S', ts)
    return ret


def string2time(s):
    """
    Parse formatted timed consistently

    s: the string produced by time2string
    return: UNIX time
    """
    parsed = time.strptime(s, '%Y%m%d-%H%M%S')
    ret    = calendar.timegm(parsed)
    return ret


