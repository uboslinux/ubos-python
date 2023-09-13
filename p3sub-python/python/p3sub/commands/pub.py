#!/usr/bin/python
#
# Run a publisher
#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#

from argparse import ArgumentTypeError
from os import makedirs
from os.path import isdir
from p3sub.publisher import Publisher
from urllib.parse import urlparse


def run( args, remainder ) :
    """
    Run this command.
    """

    if not isdir( args.feed_directory ) :
        makedirs( args.feed_directory )

    sub = Publisher( args.listen, args.feed_directory )
    sub.run()


def addSubParser( parentParser, cmdName ) :
    """
    Enable this command to add its own command-line options
    parentParser: the parent argparse parser
    cmdName: name of this command
    """
    parser = parentParser.add_parser( cmdName,                help='Run a p3sub publisher.' )
    parser.add_argument('--listen',           default=urlparse( "http://localhost:8945/feed" ), type=httpUrlOnly,
                                                              help='HTTP URL at which to serve the feed.' )
    parser.add_argument('--feed-directory',   default="feed", help='Directory that holds the feed content' )



def httpUrlOnly( u ) :
    parsed = urlparse( u )
    if parsed.scheme != 'http':
        raise ArgumentTypeError( "Only http protocol supported for serving the feed" )
    return parsed
