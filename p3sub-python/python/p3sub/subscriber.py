#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#


from http.server import BaseHTTPRequestHandler, HTTPServer
from p3sub.defs import *
from p3sub.utils import linkHeaderPars, decodeRequestPath
import ubos.logging
from urllib.parse import urlencode, urlunparse
from urllib.request import urlopen

class BaseSubscriber :
    """
    Abstract superclass for the two types of Subscribers we know.
    """

    def __init__( self, listenUri, feeduri, receivedDir, subId ) :
        self.theFeedUri     = feeduri
        self.theListenPath  = listenUri.path
        self.theReceivedDir = receivedDir
        self.theSubId       = subId
        self.theUnsubUri    = None # updated every time we receive it

        ( self.theWsHost, self.theWsPort ) = listenUri.netloc.split( ':', 2 )
        self.theWsPort      = int( self.theWsPort )


    def runListen( self ) :
        """
        Enter HTTP listening processing until interrupt
        """

        ws = SubscriberWebServer( ( self.theWsHost, self.theWsPort ), self )

        ubos.logging.info( f"Server started http://{ self.theWsHost }:{ self.theWsPort }" )

        try:
            ws.serve_forever()
        except KeyboardInterrupt:
            pass

        ws.server_close()
        ubos.logging.info( "Server stopped." )


    def putRequestReceived( self, handler ) :
        """
        A PUT request has been received

        @return: true if acceptable
        """
        ( path, query ) = decodeRequestPath( handler.path )
        linkRels = linkHeaderPars( handler.headers )

        if path != thePath :
            return False

        if P3SUB_PAR_TS not in query :
            ubos.logging.info( f"No { P3SUB_PAR_TS } in URL query" )
            return False;

        ts = stringToTs( query[P3SUB_PAR_TS] )

        if P3SUB_PAR_SUBID not in query :
            ubos.logging.info( f"No { P3SUB_PAR_SUBID } in URL query" )
            return False;

        if query[P3SUB_PAR_SUBID] != self.theSubId :
             ubos.logging.info( f"Wrong { P3SUB_PAR_SUBID } in URL query: { query[P3SUB_PAR_SUBID] }  vs { self.theSubId }" )
             return False; # FIXME

        if P3SUB_REL_PREV in linkRels :
            if self.theSenderUri and not linkRels[P3SUB_REL_PREV].startswith( self.theSenderUri ) :
                ubos.logging.info( f"Wrong { P3SUB_REL_PREV } in Link header: { linkRels[P3SUB_REL_PREV] } vs { self.theSenderUri }" )
                return False; # FIXME
            # FIXME: currently not checking that the timestamp is valid

        if not P3SUB_REL_UNSUBSCRIBE in linkRels :
            ubos.logging.info( f"No { P3SUB_REL_UNSUBSCRIBE } in message" )
            return False; # FIXME

        self.theUnsubUri = linkRels[ P3SUB_REL_UNSUBSCRIBE ];

        with open( f"{self.theReceivedDir}/{datetime.strftime( ts )}.dat", 'w' ) as writeTo :
            handler.rfile.write( writeTo )

        return True


    def generateSubId() :
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
        if self.runSubscribe() == 0 :
            self.runListen()
            self.runUnsubscribe()


    def runSubscribe( self ) :
        """
        Start a subscription with the publisher
        """

        # Determine subscription URI
        feedUriResponse = urlopen( urlunparse( self.theFeedUri ))
        if feedUriResponse.status != 200 :
            ubos.logging.info( f"Wrong status. Expected 200, was { publisherUriResponse.status }" )
            return 1

        feedUriLinkRels = linkHeaderPars( feedUriResponse.headers )
        if P3SUB_REL_SUBSCRIBE not in feedUriLinkRels :
            ubos.logging.error( f"Not a P3Sub URI, no { P3SUB_REL_SUBSCRIBE } Link header: { urlunparse( self.theFeedUri ) }" )
            return 1

        subscribeUri = urlparse( feedUriLinkRels[P3SUB_REL_SUBSCRIBE] )

        # Subscribe
        if not self.theSubId :
            self.theSubId = generateSubId()

        data = {
            P3SUB_PAR_SUBID : self.theSubId,
            P3SUB_PAR_CALLBACK : self.theListenUri
        }
        if self.theFromTs :
            data[ P3SUB_PAR_TS ] = tsToString( self.theFromTs )

        subscribeUriResponse = urlopen( urlunparse( subscribeUri ), data=bytes( urlencode( data ), 'utf-8' ), method='POST')
        if subscribeUriResponse.status != 200 :
            ubos.logging.error( f"Subscription failed, HTTP status { subscribeUriResponse.status }" )
            return 1

        subscribeUriLinkRels = linkHeaderPars( subscribeUriResponse.headers )
        if P3SUB_REL_UNSUBSCRIBE in subscribeUriLinkRels :
            self.theUnsubUri = linkRels[ P3SUB_REL_UNSUBSCRIBE ];


        else :
            ubos.logging.info( 'No unsubscribe link in subscription response' )



    def runUnsubscribe( self ) :
        """
        Cancel the subscription with the publisher
        """
        if not self.theUnsubUri :
            ubos.logging.info( 'Cannot unsubscribe, have no unsubscribe URI' )
            return 1

        data = {
            P3SUB_PAR_SUBID : self.theSubId,
        }

        unsubscribeUriResponse = urlopen( urlunparse( self.theUnsubUri ), data=bytes( urlencode( data )), method='POST' )
        if unsubscribeUriResponse.status != 200 :
            ubos.logging.error( f"Unsubscription failed, HTTP status { unsubscribeUriResponse.status }" )
            return 1



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
        self.runListen()




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
        if self.server.putRequestReceived( self ) :
            self.responseAccepted();
        else :
            self.responseRejected()


    def responseRejected( self ) :
        return super().do_PUT()


    def responseAccepted( self ) :
        self.send_response( 200 )
        self.send_header( "Content-type", "text/plain" )
        self.end_headers()
        self.wfile.write( bytes( "OK", "utf-8" ))
