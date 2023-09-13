#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#

import argparse
import importlib
import p3sub.commands
import sys
import ubos.logging
import ubos.utils

def run():
    """
    Main entry point: looks for available subcommands and
    executes the correct one.
    """
    cmdNames = ubos.utils.findSubmodules(p3sub.commands)

    parser = argparse.ArgumentParser( description='P3Sub (Push-Pull-Publish-Subscribe)')
    parser.add_argument('-v', '--verbose', action='count',       default=0,  help='Display extra output. May be repeated for even more output.')
    parser.add_argument('--logConfig',                                       help='Use an alternate log configuration file for this command.')
    parser.add_argument('--debug',         action='store_const', const=True, help='Suspend execution at certain points for debugging' )
    cmdParsers = parser.add_subparsers( dest='command', required=True )

    cmds = {}
    for cmdName in cmdNames:
        mod = importlib.import_module('p3sub.commands.' + cmdName)
        mod.addSubParser( cmdParsers, cmdName )
        cmds[cmdName] = mod

    args,remaining = parser.parse_known_args(sys.argv[1:])
    cmdName = args.command

    ubos.logging.initialize('p3sub', cmdName, args.verbose, args.logConfig, args.debug)

    if cmdName in cmdNames:
        try :
            ret = cmds[cmdName].run( args, remaining )
            exit( ret )

        except Exception as e:
            ubos.logging.fatal( str(type(e)), '--', e )

    else:
        ubos.logging.fatal('Sub-command not found:', cmdName, '. Add --help for help.' )

