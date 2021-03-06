#!/usr/bin/python
#
# Collection of utility functions.
#
# Copyright (C) 2014 and later, Indie Computing Corp. All rights reserved. License: see package.
#

import calendar
import json
import os
from pathlib import Path
import pkgutil
import pwd
import re
import subprocess
import time
import ubos.logging


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
        os.chmod( fileName, mode )


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
        os.chmod( fileName, mode )


def deleteFile( *files ) :
    """
    Delete one or more files.

    files; the files
    """

    for f in files:
        try :
            os.unlink( f )

        except Exception as e:
            ubos.logging.error( 'Cannot delete file:', e )


def mkdir( filename, mask = -1, uid = -1, gid = -1 ) :
    """
    Make a directory

    filename: path to the directory
    mask: permissions on the directory
    uname: owner of the directory
    gname: group of the directory
    return: True if successful
    """

    uid = getUid( uid )
    gid = getGid( gid )

    if mask is None :
        mask = 0o755

    dirPath = Path( filename )
    if dirPath.is_dir() :
        ubos.logging.warning( 'Directory exists already', filename )
        return True

    if dirPath.exists() :
        ubos.logging.error( 'Failed to create directory, something is there already:', filename );
        return False

    ubos.logging.trace( 'Creating directory', filename )

    ret = os.mkdir( filename )
    if ret :
        ubos.logging.error( 'Failed to create directory:', filename, ', status:', ret );

    if mask >= 0 :
        os.chmod( filename, mask )

    if uid >= 0 or gid >= 0 :
        os.chown( uid, gid, filename )

    return ret;


def symlink( oldfile, newfile, uid = -1, gid = -1 ) :
    """
    Make a symlink

    oldfile: the destination of the symlink
    newfile: the symlink to be created
    uid: owner username
    gid: group username
    """

    uid = getUid( uid )
    gid = getGid( gid )

    ubos.logging.trace( 'symlink', oldfile, newfile );

    ret = os.symlink( oldfile, newfile )
    if ret is None:
        if uid >= 0 or gid >= 0 :
            os.lchown( uid, gid, newfile )

    else :
        ubos.logging.error( 'Failed to symlink', oldfile, newfile )

    return ret


def absReadLink( path ) :
    """
    Resolve the target of a symbolic link to an absolute path.
    If this is not a symbolic link, resolve the path to an absolute path.

    path: the path
    return: the absolute path for path, or its target if path is a symbolic link
    """

    ret = os.path.realpath( path )
    return ret


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


def getUid( uname ) :
    """
    Get numerical user id, given user name. If already numerical, pass through.

    uname: the user name
    return: numerical user id
    """

    if uname is None :
        uid = os.getuid() # default is current user

    elif uname == -1 :
        uid = -1

    elif isinstance( uname, int ) :
        uid = uname;

    else :
        try :
            uinfo = pwd.getpwnam( uname )
        except :
            ubos.logging.error( 'Cannot find user. Using \'nobody\' instead:', uname )
            uinfo = pwd.getpwnam( 'nobody' );

        uid = uinfo[2]

    return uid


def getGid( gname ) :
    """
    Get numerical group id, given group name. If already numerical, pass through.

    uname: the group name
    return: numerical group id
    """

    if gname is None :
        gid = os.getgid() # default is current user

    elif gname == -1 :
        gid = -1

    elif isinstance( gname, int ) :
        gid = gname;

    else :
        try :
            ginfo = pwd.getgrnam( gname )
        except :
            ubos.logging.error( 'Cannot find group. Using \'nobody\' instead:', gname )
            ginfo = pwd.getgrnam( 'nobody' );

        gid = ginfo[2]

    return gid


def getUname( uid ) :
    """
    Get user name, given numerical user id. If already a string, pass through.

    uid: user id
    return: user name
    """

    if uid is None:
        uid = os.getUid() # default is current user

    if isinstance( uid, int ) :
        uname = os.getpwuid( uid )
        if uname is None :
            ubos.logging.error( 'Cannot find user. Using \'nobody\' instead:', uid )
            uname = 'nobody'

    else :
        uname = uid;

    return uname


def getGname( gid ) :
    """
    Get group name, given numerical group id. If already a string, pass through.

    gid: group id
    return: group name
    """

    if gid is None:
        gid = os.getgid() # default is current group

    if isinstance( gid, int ) :
        gname = os.getgrgid( gid )
        if gname is None :
            ubos.logging.error( 'Cannot find group. Using \'nogroup\' instead:', gid )
            gname = 'nogroup'

    else :
        gname = gid;

    return gname


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


