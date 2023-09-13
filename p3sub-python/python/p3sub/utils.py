#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#

from datetime import datetime
from p3sub.defs import *
import ubos.logging
from urllib.parse import parse_qs, unquote


def decodeRequestPath( pathWithQuery ) :
    splitPath = pathWithQuery.split( '?', 1 )

    query = {}
    if len( splitPath ) > 1 :
        queryString = splitPath[1]
        for pair in queryString.split( '&' ) :
            eq = pair.find( '=' )
            if eq < 0 :
                unpair = unquote( pair )
                query[unpair] = unpair
            else :
                query[ unquote( pair[0:eq] ) ] = unquote( pair[eq+1:] )

    return ( splitPath[0], query )


def linkHeaderPars( header ) :
    ret = {}

    for k in header.keys() :
        if k != 'link' :
            continue

        for v in header.get_all( k ) :
            semi = v.find( ';' )
            if semi < 0 :
                ubos.logging.info( 'Received link header with no parameter, skipping: %s', v )
                continue

            url = v[0:semi].strip()
            par = v[semi+1:].strip()

            m = re.match( 'rel="\+"', par )
            if m.matches() :
                ret[m.group(1)] = url
            else :
                ubos.logging.info( 'Could not parse Link rel: %s', v )

    return ret


def formFields( handler ) :
    if 'content-length' in handler.headers :
        length = int( handler.headers.get('content-length') )
        data   = handler.rfile.read( length )
        ret    = parse_qs( str( data, 'utf-8' ))
    else :
        ret = {}
    return ret


def stringToTs( s ) :
    ts = datetime.strptime( s, P3SUB_TS_FORMAT )
    return ts


def tsToString( ts ) :
    s = ts.strftime( P3SUB_TS_FORMAT )
    return s
