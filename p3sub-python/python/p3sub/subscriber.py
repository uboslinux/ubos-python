#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#


from http.server import BaseHTTPRequestHandler, HTTPServer
from p3sub.defs import *
from p3sub.utils import *
from random import randrange
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from urllib.request import urlopen, Request

class BaseSubscriber :
    """
    Abstract superclass for the two types of Subscribers we know.
    """

    def __init__( self, listenUri, feeduri, receivedDir, subId ) :
        self.theFeedUri     = feeduri
        self.theListenUri   = listenUri
        self.theReceivedDir = receivedDir
        self.theSubId       = subId
        self.theUnsubUri    = None # updated every time we receive it

        ( self.theWsHost, self.theWsPort ) = listenUri.netloc.split( ':', 2 )
        self.theWsPort      = int( self.theWsPort )
        self.theWsPath      = listenUri.path


    def runListen( self ) :
        """
        Enter HTTP listening processing until interrupt
        """

        ws = SubscriberWebServer( ( self.theWsHost, self.theWsPort ), self )

        print( f"INFO: Serving P3Sub subscriber endpoint at http://{ self.theWsHost }:{self.theWsPort}{ self.theWsPath } -- ^C to stop" )

        try:
            ws.serve_forever()
        except KeyboardInterrupt:
            pass

        ws.server_close()

        return 0


    def putRequestReceived( self, handler ) :
        """
        A PUT request has been received

        @return: true if acceptable
        """
        ( path, query ) = decodeRequestPath( handler.path )
        linkRels = linkHeaderPars( handler.headers )

        if path != self.theWsPath :
            return f"PUT sent to wrong path: { path } vs { self.theWsPath }"

        if P3SUB_PAR_TS not in query :
            return f"No { P3SUB_PAR_TS } in URL query"

        ts = stringToTs( query[P3SUB_PAR_TS] )

        if P3SUB_PAR_SUBID not in query :
            return f"No { P3SUB_PAR_SUBID } in URL query"

        if query[P3SUB_PAR_SUBID] != self.theSubId :
             return f"Wrong { P3SUB_PAR_SUBID } in URL query: { query[P3SUB_PAR_SUBID] }  vs { self.theSubId }"

        if P3SUB_REL_PREV in linkRels :
            if self.theFeedUri and not linkRels[P3SUB_REL_PREV].startswith( self.theFeedUri ) :
                return f"Wrong { P3SUB_REL_PREV } in Link header: { linkRels[P3SUB_REL_PREV] } vs { self.theFeedUri }"

            # FIXME: currently not checking that the timestamp is valid

        if not P3SUB_REL_UNSUBSCRIBE in linkRels :
            return f"No { P3SUB_REL_UNSUBSCRIBE } in message"

        self.theUnsubUri = relativeToAbsoluteUrl( self.theFeedUri, urlparse( linkRels[P3SUB_REL_UNSUBSCRIBE] ))

        contentLength = int( handler.headers['content-length'] )

        with open( f"{self.theReceivedDir}/{ts.strftime( '%Y-%m-%dT%H:%M:%S.%fZ.dat' )}", 'wb' ) as writeTo :
            buf = handler.rfile.read( contentLength )
            writeTo.write( buf )

        return None


    def generateSubId( self ) :
        ret = ''
        values = "ABCDEFGHIJKLMNOPQRSTUVWabcdefghijklmnopqrstuvwxyz0123456789_"
        for i in range(0,38) : # at least 32 char
            ret = ret + values[ randrange( len( values )) ]
        return ret


class SubscribingSubscriber( BaseSubscriber ):
    """
    This version subscribes first and unsubscribes upon quit
    """
    def __init__( self, listenUri, receivedDir, feeduri, diff, fromTs ) :
        super().__init__( listenUri, feeduri, receivedDir, None )

        self.theDiff   = diff;
        self.theFromTs = fromTs;


    def run( self ) :
        """
        Run the subscriber command.
        """
        err = self.runSubscribe()

        if not err :
            err = self.runListen()

        if not err :
            err = self.runUnsubscribe()

        return err


    def runSubscribe( self ) :
        """
        Start a subscription with the publisher
        """

        # Determine subscription URI
        feedUriResponse = urlopen( urlunparse( self.theFeedUri ))
        if feedUriResponse.status != 200 :
            return f"Wrong status. Expected 200, was { publisherUriResponse.status }"

        feedUriLinkRels = linkHeaderPars( feedUriResponse.headers )
        if P3SUB_REL_SUBSCRIBE not in feedUriLinkRels :
            return f"Not a P3Sub URI, no { P3SUB_REL_SUBSCRIBE } Link header: { urlunparse( self.theFeedUri ) }"

        subscribeUri = relativeToAbsoluteUrl( self.theFeedUri, urlparse( feedUriLinkRels[P3SUB_REL_SUBSCRIBE] ))

        # Subscribe
        if not self.theSubId :
            self.theSubId = self.generateSubId()

        data = {
            P3SUB_PAR_SUBID : self.theSubId,
            P3SUB_PAR_CALLBACK : urlunparse( self.theListenUri )
        }
        if self.theFromTs :
            data[ P3SUB_PAR_TS ] = tsToString( self.theFromTs )

        subscribeUriResponse = urlopen( Request( urlunparse( subscribeUri ), data=bytes( urlencode( data ), 'utf-8' ), method='POST' ))
        if subscribeUriResponse.status != 200 :
            return f"Subscription failed, HTTP status { subscribeUriResponse.status }"

        subscribeUriLinkRels = linkHeaderPars( subscribeUriResponse.headers )
        if P3SUB_REL_UNSUBSCRIBE in subscribeUriLinkRels :
            self.theUnsubUri = relativeToAbsoluteUrl( self.theFeedUri, urlparse( subscribeUriLinkRels[P3SUB_REL_UNSUBSCRIBE] ))

        else :
            return 'No unsubscribe link in subscription response'

        return None


    def runUnsubscribe( self ) :
        """
        Cancel the subscription with the publisher
        """

        if not self.theUnsubUri :
            return 'Cannot unsubscribe, have no unsubscribe URI'

        data = {
            P3SUB_PAR_SUBID : self.theSubId,
        }
        unsubscribeUriResponse = urlopen( Request( urlunparse( self.theUnsubUri ), data=bytes( urlencode( data ), 'utf-8' ), method='POST' ))
        if unsubscribeUriResponse.status != 200 :
            return f"Unsubscription failed, HTTP status { unsubscribeUriResponse.status }"

        return None


class PassiveSubscriber( BaseSubscriber ) :
    """
    This version does not subscribe or unsubscribe but merely listens
    """
    def __init__( self, listenUri, receivedDir, subId ) :
        super().__init__( listenUri, None, receivedDir, subId )


    def run( self ) :
        """
        Run the subscriber command.
        """
        return self.runListen()


class SubscriberWebServer( HTTPServer ) :
    """
    The default HTTPServer instantiates request handlers entirely without
    context; there is no way of passing in local data. So
    we override the internal factory method.
    """
    def __init__( self, server_address, subscriber, bind_and_activate=True ):
        HTTPServer.__init__( self, server_address, SubscriberPutRequestHandler, bind_and_activate )

        self.theSubscriber = subscriber


    def putRequestReceived( self, handler ) :
        return self.theSubscriber.putRequestReceived( handler )


class SubscriberPutRequestHandler( BaseHTTPRequestHandler ) :

    def do_PUT( self ):
        self.complete( self.server.putRequestReceived( self ))


    def complete( self, err ) :
        if err :
            self.send_response( 400 )
            self.send_header( "Content-type", "text/plain" )
            self.end_headers()
            self.wfile.write( bytes( f"ERROR: Cannot serve this request.\n{ err }\n", "utf-8" ))
        else :
            self.send_response( 200 )
            self.send_header( "Content-type", "text/plain" )
            self.end_headers()
            self.wfile.write( bytes( "OK", "utf-8" ))
