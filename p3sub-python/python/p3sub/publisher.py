#
# Copyright (C) Johannes Ernst. All rights reserved. License: see package.
#

from collections import namedtuple
from datetime import timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from os import listdir
from os.path import isfile, getmtime
from p3sub.defs import *
from p3sub.utils import *
import ubos.logging
from urllib.parse import urlparse
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class Publisher :
    def __init__( self, listenUri, feedDirectory ) :
        self.theFeedDirectory = PublisherFeedDirectory( feedDirectory )
        self.theOutQueue      = PublisherOutQueue()

        ( self.theWsHost, self.theWsPort ) = listenUri.netloc.split( ':', 2 )
        self.theWsPort          = int( self.theWsPort )
        self.theFeedPath        = listenUri.path
        self.theSubscribePath   = self.theFeedPath + '/sub'
        self.theUnsubscribePath = self.theFeedPath + '/unsub'
        self.theSubscriptions   = {} # subId -> { uri, lastTsEnqueued }


    def run( self ) :
        """
        Run the publisher command.
        """

        # observe the feed directory
        observer = Observer()
        observer.schedule( ObserverEventHandler( self.theFeedDirectory ), self.theFeedDirectory.getDirectory(), recursive=False)
        observer.start()

        # run a web server
        ws = PublisherWebServer( ( self.theWsHost, self.theWsPort ), self )

        ubos.logging.info( f"Server started http://{ self.theWsHost }:{ self.theWsPort }" )

        try:
            ws.serve_forever()
        except KeyboardInterrupt:
            pass

        ws.server_close()
        observer.stop()
        observer.join()


    def feedRequestReceived( self, handler ) :
        ( path, query ) = decodeRequestPath( handler.path )
        if P3SUB_PAR_TS in query :
            ts = stringToTs( query[P3SUB_PAR_TS] )
        else :
            ts = None

        if ts :
            elWithBeforeAfter = self.theFeedDirectory.elementAtWithBeforeAfter( ts )
        else :
            elWithBeforeAfter = self.theFeedDirectory.currentElementWithBeforeAfter()

        if elWithBeforeAfter is None:
            handler.send_response( 404 )
            handler.send_header( "Content-type", "text/plain" )
            handler.end_headers()
            handler.wfile.write( bytes( "No such element.\n", "utf-8" ))
        else :
            handler.send_response( 200 )
            handler.send_header( "Content-type", "text/plain" )
            handler.send_header( "link", f'<{ self.theFeedPath }?{ P3SUB_PAR_TS }={ tsToString( elWithBeforeAfter[1].mtime ) }>; rel="{ P3SUB_REL_CANONICAL }"' );
            handler.send_header( "link", f'<{ self.theSubscribePath }>; rel="{ P3SUB_REL_SUBSCRIBE }"' );
            if elWithBeforeAfter[0] is not None :
                handler.send_header( "link", f'<{ self.theFeedPath }?{ P3SUB_PAR_TS }={ tsToString( elWithBeforeAfter[0].mtime ) }>; rel="{ P3SUB_REL_PREV }"' );
            if elWithBeforeAfter[2] is not None :
                handler.send_header( "link", f'<{ self.theFeedPath }?{ P3SUB_PAR_TS }={ tsToString( elWithBeforeAfter[2].mtime ) }>; rel="{ P3SUB_REL_NEXT }"' );
            handler.end_headers()
            with open( elWithBeforeAfter[1].name, 'rb' ) as f :
                for fBlock in iter( partial( f.read, 1024 ), b'' ) :
                    handler.wfile.write( fBlock )
        return None


    def subscribeRequestReceived( self, handler ) :
        postData = formFields( handler )

        if P3SUB_PAR_SUBID not in postData :
            return f'No { P3SUB_PAR_SUBID } in POSTed data for subscribe request'
        subId = postData[P3SUB_PAR_SUBID]
        if type( subId ) is list :
            if len( subId ) > 1 :
                return f'Too many { P3SUB_PAR_SUBID } in POSTed data for subscribe request'
            subId = subId[0]
        if len( subId ) < 32 :
            return f'Parameter { P3SUB_PAR_SUBID } must have a value of at least 32 characters'

        if P3SUB_PAR_CALLBACK not in postData :
            return f'No { P3SUB_PAR_CALLBACK } in POSTed data for subscribe request'
        callback = postData[P3SUB_PAR_CALLBACK]
        if type( callback ) is list :
            if len( callback ) > 1 :
                return f'Too many { P3SUB_PAR_CALLBACK } in POSTed data for subscribe request'
            callback = callback[0]
        callbackUri = urlparse( callback )
        if not callbackUri.scheme:
            return f'Not a valid callback URI: { callback }'

        if P3SUB_PAR_TS in postData:
            fromTs = postData[P3SUB_PAR_TS]
            if type( fromTs ) is list :
                if len( fromTs ) > 1 :
                    return f'Too many { P3SUB_PAR_TS } in POSTed data for subscribe request'
                fromTs = fromTs[0]
            fromTs = stringToTs( fromTs )
        else :
            fromTs = datetime.today()

        self.theSubscriptions[ subId ] = PublisherSubscription( callbackUri, fromTs )

        self.logSubscriptions()

        toQueue = self.theFeedDirectory.elementsAfterWithBefore( fromTs )
        if toQueue[1] :
            previous = toQueue[0]
            for data in toQueue[1] :
                self.theOutQueue.enqueueToSend( callback, previous, data )
                previous = data

        handler.send_response( 200 )
        handler.send_header( "Content-type", "text/plain" )
        handler.send_header( "link", f'<{ self.theUnsubscribePath }>; rel="{ P3SUB_REL_UNSUBSCRIBE }"' );
        handler.end_headers()
        handler.wfile.write( bytes( "Subscription successful.\n", "utf-8" ))

        return None


    def unsubscribeRequestReceived( self, handler ) :
        postData = formFields( handler )

        if P3SUB_PAR_SUBID not in postData :
            return f'No { P3SUB_PAR_SUBID } in POSTed data for unsubscribe request'
        subId = postData[P3SUB_PAR_SUBID]
        if type( subId ) is list :
            if len( subId ) > 1 :
                return f'Too many { P3SUB_PAR_SUBID } in POSTed data for subscribe request'
            subId = subId[0]

        if subId in self.theSubscriptions :
            del self.theSubscriptions[ subId ]

            self.logSubscriptions()

            handler.send_response( 200 )
            handler.send_header( "Content-type", "text/plain" )
            handler.send_header( "link", f'<{ self.theSubscribePath }>; rel="{ P3SUB_REL_SUBSCRIBE }"' );
            handler.end_headers()
            handler.wfile.write( bytes( "Unsubscription successful.\n", "utf-8" ))
            return None

        else :
            return f"No subscription found with { P3SUB_PAR_SUBID }={ subId }.\n"


    def getRequestReceived( self, handler ) :
        ( path, query ) = decodeRequestPath( handler.path )
        if path == self.theFeedPath :
            ret = self.feedRequestReceived( handler )
        else :
            ret = 1
        return ret


    def postRequestReceived( self, handler ) :
        ( path, query ) = decodeRequestPath( handler.path )
        if path == self.theSubscribePath :
            ret = self.subscribeRequestReceived( handler )
        elif path == self.theUnsubscribePath :
            ret = self.unsubscribeRequestReceived( handler )
        else :
            ret = 1
        return ret


    def logSubscriptions( self ) :
        print( f"Subscriptions now: { len( self.theSubscriptions ) }" )
        for sId in self.theSubscriptions :
            subscription = self.theSubscriptions[sId]
            print( f'    { sId }: { subscription.callbackUri } (last success: { subscription.lastSuccessfulTs })' )


class PublisherSubscription( namedtuple( 'PublisherSubscription', [ 'callbackUri', 'lastSuccessfulTs' ] )) :
    pass


class PublisherWebServer( HTTPServer ) :
    """
    The default HTTPServer instantiates request handlers entirely without
    context; there is no way of passing in local data. So
    we override the internal factory method.
    """
    def __init__( self, server_address, publisher, bind_and_activate=True ):
        HTTPServer.__init__( self, server_address, PublisherRequestHandler, bind_and_activate )

        self.thePublisher = publisher


class PublisherRequestHandler( BaseHTTPRequestHandler ) :
    def do_GET( self ):
        try :
            self.complete( self.server.thePublisher.getRequestReceived( self ))
        except BaseException as ex:
            self.complete( 'An internal error occurred: ' + str( ex ))
            raise


    def do_POST( self ):
        try :
            self.complete( self.server.thePublisher.postRequestReceived( self ))
        except BaseException as ex:
            self.complete( 'An internal error occurred: ' + str( ex ))
            raise


    def complete( self, err ) :
        if err :
            self.send_response( 400 )
            self.send_header( "Content-type", "text/plain" )
            self.end_headers()
            self.wfile.write( bytes( f"ERROR: Cannot serve this request.\n{ err }\n", "utf-8" ))


class PublisherFeedDirectory :
    def __init__( self, directory ) :
        self.theDirectory          = directory;
        self.theElementsInSequence = None


    def getDirectory( self ) :
        return self.theDirectory


    def currentElementWithBeforeAfter( self ) :
        self.ensureElementsInSequence()
        if len( self.theElementsInSequence ) > 1 :
            return ( self.theElementsInSequence[-2], self.theElementsInSequence[-1], None )

        elif( len( self.theElementsInSequence ) > 0 ) :
            return ( None, self.theElementsInSequence[-1], None )

        else :
            return None


    def elementAtWithBeforeAfter( self, ts ) :
        self.ensureElementsInSequence()
        # We need to search, as ts may not be exact
        length = len( self.theElementsInSequence )
        for i in range( length-1, -1, -1 ) :
            el = self.theElementsInSequence[i]
            if el.mtime <= ts :
                if i>0 :
                    if i<length-1 :
                        return ( self.theElementsInSequence[i-1], el, self.theElementsInSequence[i+1] )
                    else :
                        return ( self.theElementsInSequence[i-1], el, None )
                else :
                    if i<length-1 :
                        return ( None, el, self.theElementsInSequence[i+1] )
                    else :
                        return ( None, el, None )

        return None


    def elementsAfterWithBefore( self, ts ) :
        self.ensureElementsInSequence()
        for i in range( 0, len( self.theElementsInSequence )) :
            el = self.theElementsInSequence[i]
            if el.mtime <= ts :
                continue

            if i>0 :
                return ( self.theElementsInSequence[i-1], self.theElementsInSequence[i:] )
            else :
                return ( None, self.theElementsInSequence[i:] )
        return ( None, None )


    def ensureElementsInSequence( self ) :
        if self.theElementsInSequence is None :
            files              = listdir( self.theDirectory )
            elementsInSequence = []

            for f in files :
                realF = self.theDirectory + '/' + f
                if not isfile( realF ) :
                    continue

                elementsInSequence.append( PublisherFeedDirectoryElement( name=realF, mtime=datetime.fromtimestamp( getmtime( realF ), timezone.utc )))

            elementsInSequence = sorted( elementsInSequence, key = lambda e : e.mtime )
            self.theElementsInSequence = elementsInSequence

            print( "Updated list of feed data elements:" )
            for el in self.theElementsInSequence :
                print( f"    name = { el.name }, ts = { tsToString( el.mtime ) }" )

        return self.theElementsInSequence


    def purgeElementsInSequence( self ) :
        self.theElementsInSequence = None


class PublisherFeedDirectoryElement( namedtuple( 'PublisherFeedDirectoryElement', [ 'name', 'mtime' ])) :
    def __str__( self ) :
        return f"PublisherFeedDirectoryElement( name={ self.name }, mtime={ self.mtime } )"


class ObserverEventHandler( FileSystemEventHandler ) :
    def __init__( self, feedDirectory ) :
        super().__init__()
        self.theFeedDirectory = feedDirectory


    def on_any_event( self, event ) :
        # We take the easy way out
        self.theFeedDirectory.purgeElementsInSequence()


class PublisherOutQueue :
    def enqueueToSend( self, uri, previous, data ) :
        print( f"XXX About the send { data } with previous { previous } to { uri }." )
