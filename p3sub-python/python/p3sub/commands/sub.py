#!/usr/bin/python
#
# Run a subscriber
#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#

from argparse import ArgumentTypeError
from os import makedirs
from os.path import isdir
from p3sub.utils import *
from p3sub.subscriber import SubscribingSubscriber, PassiveSubscriber
from urllib.parse import urlparse


def run( args, remainder ) :
    """
    Run this command.
    """
    if args.subscriptionid :
        if args.feeduri :
            raise ArgumentTypeError( "Specify feeduri or subscriptionid, not both" )

        if args.diff :
            raise ArgumentTypeError( "Cannot specify --diff when specifying --subscriptionid" )

        if args.from_ts :
            raise ArgumentTypeError( "Cannot specify --from-ts when specifying --subscriptionid" )

    if not isdir( args.received_directory ) :
        makedirs( args.received_directory )

    if args.subscriptionid :
        sub = PassiveSubscriber( args.listen, args.received_directory, args.subscriptionid )
    else :
        sub = SubscribingSubscriber( args.listen, args.received_directory, args.feeduri, args.diff, args.from_ts )

    sub.run()


def addSubParser( parentParser, cmdName ) :
    """
    Enable this command to add its own command-line options
    parentParser: the parent argparse parser
    cmdName: name of this command
    """
    parser = parentParser.add_parser( cmdName,                      help='Run a p3sub subscriber.' )
    parser.add_argument('--listen',             default=( urlparse( 'http://localhost:8946/' )), type=httpUrlOnly,
                                                                    help='HTTP URL at which to listen to incoming feed elements.' )
    parser.add_argument('--received-directory', default='received', help='Store received feed elements in this directory.' )

    # This mutual exclusivity isn't quite right, but then argparse does not like me to put more than one argument into
    # one option of the mutually exclusive group
    subscribingMode = parser.add_mutually_exclusive_group( required=True )
    subscribingMode.add_argument('feeduri', nargs='?',           type=httpUrl,    help='URI of the feed.' )
    subscribingMode.add_argument( '--subscriptionid', '--subid', type=validSubId, help="Use this existing SUBID; do not subscribe again" )

    parser.add_argument('--diff',    default=False, help='Subscribe in "diff" mode.' )
    parser.add_argument('--from-ts', type=validTs,  help='Subscribe from this timestamp' )


def httpUrl( u ) :
    parsed = urlparse( u )
    if parsed.scheme != 'http' and parsed.scheme != 'https':
        raise ArgumentTypeError( "Only http and https protocol supported for feeds to subscribe to" )
    return parsed


def httpUrlOnly( u ) :
    parsed = urlparse( u )
    if parsed.scheme != 'http':
        raise ArgumentTypeError( "Only http protocol supported for incoming feed elements" )
    return parsed


def validSubId( s ) :
    if len( s ) < 32 :
        raise ArgumentTypeError( "Subscription id must have at least 32 characters" )
    return s


def validTs( s ) :
    return stringToTs( s, P3SUB_TS_FORMAT )
