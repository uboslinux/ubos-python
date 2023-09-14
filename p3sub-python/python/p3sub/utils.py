#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#

from datetime import datetime
from p3sub.defs import *
import re
import ubos.logging
from urllib.parse import parse_qs, unquote, ParseResult

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
        if k.lower() != 'link' :
            continue

        for v in header.get_all( k ) :
            for v2 in v.split( ',' ) :
                # can be multiple values on the same line

                semi = v2.find( ';' )
                if semi < 0 :
                    # Received link header with no parameter, skipping
                    continue

                url = v2[0:semi].strip()
                par = v2[semi+1:].strip()

                if url.startswith( '<' ) :
                    url = url[1:]
                if url.endswith( '>' ) :
                    url = url[0:-1]

                m = re.fullmatch( 'rel="([^"]+)"', par )
                if m :
                    ret[m.group(1)] = url
                else :
                    print( f"WARNING: Could not parse Link rel: { v }" )

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
    ts = datetime.strptime( s, '%Y-%m-%dT%H:%M:%S.%f%z' )
    return ts


def tsToString( ts ) :
    s = ts.strftime( '%Y-%m-%dT%H:%M:%S.%fZ' )
    # I can't get python to emit the Z for the timezone
    return s


def relativeToAbsoluteUrl( base, relative ) :
    if base is None :
        return relative

    if relative is None :
        return base

    if relative.scheme :
        return relative

    scheme = base.scheme
    netloc = relative.netloc if relative.netloc else base.netloc

    if relative.path.startswith( '/' ) :
        path = relative.path
    else :
        lastSlash = base.path.rfind( '/' )
        if lastSlash >= 0 :
            path = base.path[0:lastSlash+1] + relative.path
        else :
            path = '/' + relative.path

    return ParseResult( scheme, netloc, path, relative.params, relative.query, relative.fragment )
