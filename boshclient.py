"""
BOSH Client
-----------

Quite simple BOSH client used by Django-XMPPAuth
For now, it only supports the DIGEST-MD5 text authentication method.
You must install Twisted. Here is how to with Pip: pip install twisted

TODO: write the SASL MD5 function: installing twisted (2.5Mb) just for the
SASL part is too much.
TODO: write the PLAIN authentication.
TODO: make shortcuts functions (example: connect + bosh session + auth).
TODO: make an interactive mode for the client (or just use Python??).
TODO: add namespaces as global variables
"""

import httplib, sys, random
from base64 import b64decode, b64encode
from urlparse import urlparse
from xml.dom import minidom

from twisted.words.protocols.jabber.sasl_mechanisms import DigestMD5


NS_COMMANDS = 'http://jabber.org/protocol/commands'

class ConnectionError(Exception):
    """Error raised when connection with server failed"""
    pass


class BOSHClient:
    """
    Quite simple BOSH client used by Django-XMPPAuth.
    When you initialize the client, it does NOT connect! Here is a mock 
    connection process with the BOSH Client:
    
    >>> client = BOSHClient('http://debian/http-bind/', 'essai@debian', 'essai', resource='web', debug=False)
    >>> client.init_connection()
    >>> client.request_bosh_session()
    >>> sid = client.authenticate_xmpp()
    >>> client.close_connection()
    """
    
    def __init__(self, bosh_service, jid='', password='', resource='web', debug=True):
        """
        Initialize the client.
        You must specify the Jabber ID, the corresponding password and the URL
        of the BOSH service to connect to.
        """

        self.debug = debug
        
        self.connection = None
        
        if jid:
            self.jid = JID(jid, resource)
        else:
            self.jid = ''
        self.password = password
        self.bosh_service = urlparse(bosh_service)
        self.resource = resource
        
        self.rid = random.randint(0, 10000000)
        self.log('Init RID: %s' % self.rid)
        
        self.content_type = "text/xml; charset=utf-8"
        self.headers = {
            "Content-type": "text/plain; charset=UTF-8",
            "Accept": "text/xml",
        }
        
        self.server_auth = []
    
    def log(self, message):
        """
        Print a message in the standard output. Warning: this function makes the
        client very verbose!
        """
        if self.debug:
            print '[DEBUG] ' + message
    
    def get_sid(self):
        """Return the SID assigned to this client"""
        return self.sid
    
    def get_rid(self):
        """Return the RID of this client"""
        return self.rid
    
    def set_rid(self, rid=0):
        """
        Create a random RID and use it, except if rid is specified and different
        from 0.
        """
        if rid == 0:
            self.rid = random.randint(0, 10000000)
        else:
            self.rid = rid
    
    def init_connection(self):
        """Initialize the HTTP connection (not the XMPP session!)"""
        self.log('Initializing connection to %s' % (self.bosh_service.netloc))
        self.connection = httplib.HTTPConnection(self.bosh_service.netloc)
        self.log('Connection initialized')
        # TODO add exceptions handler there (URL not found etc)
    
    def close_connection(self):
        """Close the HTTP connection (not the XMPP session!)"""
        self.log('Closing connection')
        self.connection.close()
        self.log('Connection closed')
        # TODO add execptions handler there

    def wrap_stanza_body(self, stanza, more_body=''):
        """Wrap the XMPP stanza with the <body> element (required for BOSH)"""
        if not stanza == '':
            return "<body rid='%s' sid='%s' %s xmlns='http://jabber.org/protocol/httpbind'>%s</body>" % (self.rid, self.sid, more_body, stanza)
        else:
            return "<body rid='%s' sid='%s' %s xmlns='http://jabber.org/protocol/httpbind' />" % (self.rid, self.sid, more_body)

    def send_request(self, xml_stanza):
        """
        Send a request to self.bosh_service.path using POST containing
        xml_stanza with self.headers.
        Returns the data contained in the response (only if status == 200)
        Returns False if status != 200
        """
        self.log('XML_STANZA:')
        self.log(xml_stanza)
        self.log('Sending the request')
        try:
            self.connection.request("POST", self.bosh_service.path, xml_stanza, self.headers)
        except AttributeError:
            raise ConnectionError
            return False
        self.rid += 1
        response = self.connection.getresponse()
        data = ''
        self.log('Response status code: %s' % response.status)
        if response.status == 200:
            data = response.read()
        else:
            self.log('Something wrong happened!')
            return False
            
        self.log('DATA:')
        self.log(data)
        return data
    
    def register(self, **kwargs):
        """
        Create a new user account on the XMPP server, according to XEP-0077 
        http://xmpp.org/extensions/xep-0077.html
        """

        self.log('Ask the remote server to send the fields list.')
        xml_stanza = self.wrap_stanza_body("<iq type='get' id='reg1'><query xmlns='jabber:iq:register'/></iq>")
        data = self.send_request(xml_stanza)
        # The servers send the fields list and an instruction element.
        fields = []
        response_body = minidom.parseString(data).documentElement
        query = response_body.getElementsByTagName('query')[0]
        for child in query.childNodes:
            if child.localName == 'instructions':
                # This node is the instruction element
                # TODO: find a smart thing to do with this information
                pass
            else:
                fields.append(child.localName)
        # It's time to build the dictonary for the response
        response_dict = {}
        for element in fields:
            response_dict[element] = kwargs.get(element, '')
        # And now, build the response XML stanza
        xml_stanza_top = "<iq type='set' id='reg2'><query xmlns='jabber:iq:register'>"
        xml_stanza_bottom = "</query></iq>"
        xml_stanza = xml_stanza_top
        for elem, value in response_dict.iteritems():
            xml_stanza = xml_stanza + "<%s>%s</%s>" % (elem, value, elem)
        xml_stanza = xml_stanza + xml_stanza_bottom
        # Then send it
        data = self.send_request(self.wrap_stanza_body(xml_stanza))
        
        # TODO: handle exceptions (conflict, not-acceptable etc)
    
    def request_bosh_session(self):
        """
        Request a BOSH session according to
        http://xmpp.org/extensions/xep-0124.html#session-request
        Returns the new SID (str).
        This function also fill many fields of this BOSHClient object, such as:
            * sid
            * server_wait
            * server_auth_methods
        """
        self.log('Prepare to request BOSH session')
        
        xml_stanza = "<body rid='%s' xmlns='http://jabber.org/protocol/httpbind' to='%s' xml:lang='en' wait='60' hold='1' window='5' content='text/xml; charset=utf-8' ver='1.6' xmpp:version='1.0' xmlns:xmpp='urn:xmpp:xbosh'/>" % (self.rid, self.jid.host)
        data = self.send_request(xml_stanza)
      
        # This is XML. response_body contains the <body/> element of the
        # response.
        try:
            response_body = minidom.parseString(data).documentElement
        except TypeError:
            raise ConnectionError
            return 0;
        
        # Check if this there was a problem during the session request
        if response_body.getAttribute('type') == 'terminate':
            return 0;
        
        # Get the remote Session ID
        self.sid = response_body.getAttribute('sid')
        self.log('sid = %s' % self.sid)
        
        # Get the longest time (s) that the XMPP server will wait before
        # responding to any request.
        self.server_wait = response_body.getAttribute('wait')
        self.log('wait = %s' % self.server_wait)
        
        # Get the authid
        self.authid = response_body.getAttribute('authid')
        
        # Get the allowed authentication methods
        stream_features = response_body.firstChild
        auth_list = []
        try:
            mechanisms = stream_features.getElementsByTagNameNS('urn:ietf:params:xml:ns:xmpp-sasl', 'mechanisms')[0]
            if mechanisms.hasChildNodes():
                for child in mechanisms.childNodes:
                    auth_method = child.firstChild.data
                    auth_list.append(auth_method)
                    self.log('New AUTH method: %s' % auth_method)
            
                self.server_auth = auth_list
                
            else:
                self.log('The server didn\'t send the allowed authentication methods')
        except AttributeError:
            self.log('The server didn\'t send the allowed authentication methods')
            
            # FIXME: BIG PROBLEM THERE! AUTH METHOD MUSTN'T BE GUEST!
            auth_list = ['DIGEST-MD5']
            self.server_auth = auth_list
        
        #return self.sid
        
    def xmpp_disco(self):
        """
        Retrieve informations about the server services using the Jabber 
        informations discovering.
        http://xmpp.org/extensions/xep-0030.html
        """
        self.log('Using DISCO')
        xml_stanza = self.wrap_stanza_body("<iq type='get' from='%s' to='%s' id='info1'><query xmlns='http://jabber.org/protocol/disco#info'/></iq>" % (self.jid.jid_with_resource, self.jid.host))
        data = self.send_request(xml_stanza)

    def xmpp_disco_node(self, node_name):
        """
        Discover the given node.
        http://xmpp.org/extensions/xep-0030.html#items
        """
        self.log('DISCO the node %s' % node_name)
        xml_stanza = self.wrap_stanza_body("<iq type='get' from='%s' to='%s' id='info2'><query xmlns='http://jabber.org/protocol/disco#info' node='http://jabber.org/protocol/%s'/></iq>" % (self.jid.jid_with_resource, self.jid.host, node_name))
        data = self.send_request(xml_stanza)
    
    def authenticate_xmpp(self):
        """
        Authenticate the user to the XMPP server via the BOSH connection.
        You MUST have the following settings set:
            * self.sid
            * self.jid
            * self.password
            * self.rid
            * self.server_auth
        Note also that the connection MUST be opened (see self.init_connection).
        Returns True if the authenication went fine, otherwise, returns False.
        """
        
        self.log('Prepare the XMPP authentication')
            
        if 'DIGEST-MD5' in self.server_auth:
            self.log('Authenticate with DIGEST-MD5')
            
            # Ask for the MD5 challenge
            xml_stanza = "<body rid='%s' xmlns='http://jabber.org/protocol/httpbind' sid='%s'><auth xmlns='urn:ietf:params:xml:ns:xmpp-sasl' mechanism='DIGEST-MD5'/></body>" % (self.rid, self.sid)
            data = self.send_request(unicode(xml_stanza))
        
            # Decode the challenges
            continue_challenges = True
            while continue_challenges:
                hash = minidom.parseString(data).documentElement.getElementsByTagName('challenge')[0].firstChild.data
                decoded = b64decode(hash)
                self.log('Decoded challenge: %s' % decoded)
                
                # Prepare the response
                digest_object = DigestMD5('xmpp', self.jid.host, None, self.jid.user, self.password)
                response = b64encode(digest_object.getResponse(decoded))
                self.log('Reponse to challenge: %s' % response)
                xml_stanza = self.wrap_stanza_body("<response xmlns='urn:ietf:params:xml:ns:xmpp-sasl'>%s</response>" % response)
                data = self.send_request(xml_stanza)
                if not minidom.parseString(data).documentElement.getElementsByTagName('challenge'):
                    # It's not a challenge
                    continue_challenges = False
            
            # Check if we succeed the handshake
            is_success = minidom.parseString(data).documentElement.getElementsByTagName('success')
            if is_success:
                # Oh yeah it rocks!
                self.log('Authentication succeeded!')
            else:
                # Shit. So bad :( so just read the code, fix the problem and
                # commit !
                self.log('Authentication failed!')
                return  False
            
            # Ask the server to restart the stream
            self.log('Asking the server to restart the stream')
            xml_stanza = self.wrap_stanza_body('', "to='%s' xml:lang='en' xmpp:restart='true' xmlns:xmpp='urn:xmpp:xbosh'" % self.jid.host)
            data = self.send_request(xml_stanza)
            self.log('The stream just restarted')
            
            # Bind the resource
            self.log('Binding the resource')
            xml_stanza = self.wrap_stanza_body("<iq id='bind_1' type='set' xmlns='jabber:client'><bind xmlns='urn:ietf:params:xml:ns:xmpp-bind'><resource>%s</resource></bind></iq>" % self.resource)
            data = self.send_request(xml_stanza)
            self.log('The resource got bound to: %s' % self.resource)

            # Establish the IM session
            self.log('Establishing the IM session')
            xml_stanza = self.wrap_stanza_body("<iq type='set' id='bind_2'><session xmlns='urn:ietf:params:xml:ns:xmpp-session'/></iq>")
            data = self.send_request(xml_stanza)
            self.log('IM session established')            

            return True
            
        elif 'PLAIN' in self.server_auth:
            
            #
            # PLAIN authentication isn't finished (== it doesn't work)
            #
            
            self.log('Authenticate with PLAIN text')
            
            # Request authentication fields
            xml_stanza = self.wrap_stanza_body("<iq type='get' to='%s' id='auth1'><query xmlns='jabber:iq:auth'/></iq>" % self.jid.host)
            data = self.send_request(xml_stanza)
     
    def disconnect(self):
        """Gracefully terminate the session"""
        self.log("Terminating the XMPP session")
        xml_stanza = self.wrap_stanza_body("<presence type='unavailable' xmlns='jabber:client'/>", "type='terminate'")
        self.send_request(xml_stanza)
        self.log("Session terminated")
        
        
class AdminBOSHClient(BOSHClient):
    """
    This is an extended version of the BOSHClient with all the administration
    functions, such as ad-hoc commands
    (http://xmpp.org/extensions/xep-0050.html) for administration uses:
    http://xmpp.org/extensions/xep-0133.html.
    Be careful: if you use AdminBOSHClient and the user that you log in isn't
    and administrator, all your commands will return the tuple:
    (-1,'Your are not an administrator)
    Have fun.
    
    
    >>> client = AdminBOSHClient('http://debian/http-bind/', jid='thomas@debian', password='password', resource='boshclient', debug=False)
    >>> client.init_connection()
    >>> client.request_bosh_session()
    >>> sid = client.authenticate_xmpp()
    >>> client.get_registred_users()
    10
    >>> client.close_connection()
    """
    
    def __init__(self, bosh_service, jid='', password='', resource='boshclient', debug=True):
        """Initialize the client, just like the BOSHClient"""
        BOSHClient.__init__(self, bosh_service, jid, password, resource, debug)
        
        self.ad_hoc_commands = {
            'get-registred-users-num': 0,
            'add-user': 0,
        }
    
    def get_id(self, name):
        """
        Increases the command counter and returns the id field.
        """
        self.ad_hoc_commands[name] += 1
        string = "%s-%s" % (name, self.ad_hoc_commands[name])
        return string
    
    def add_user(self, username, password):
        """
        Create a new user account on the XMPP server.
        http://xmpp.org/extensions/xep-0133.html#add-user
        """
        
        self.log('ADD-USER ask the server for the form.')
        id = self.get_id('add-user')
        xml_stanza = self.wrap_stanza_body("<iq from='%s' id='%s' to='%s' type='set' xml:lang='en'><command xmlns='http://jabber.org/protocol/commands' action='execute' node='http://jabber.org/protocol/admin#add-user'/></iq>" % (self.jid.jid_with_resource, id, self.jid.host))
        data = self.send_request(xml_stanza)
    
    def get_registred_users(self):
        """
        Retrieve the number of registred users.
        http://xmpp.org/extensions/xep-0133.html#get-registered-users-num
        """
        self.log('Retrieving the registred users number')
        id = self.get_id('get-registred-users-num')
        command = AdHocCommand(self.jid.jid_with_resource, id=id, to=self.jid.host, type='set')
        command.set_command(xmlns=NS_COMMANDS, action='execute', node='http://jabber.org/protocol/admin#get-registered-users-num')
        self.log('XML: %s' % command.string())
        xml_stanza = self.wrap_stanza_body(command.string())
        data = self.send_request(xml_stanza)


class AdHocCommand:
    """Extensible way to implement ad hoc commands"""

    def __init__(self, jid, **kwargs):
        """
        The keywords arguments specifythe parameters of the <iq> element. Use
        set_command with kwargs to set the <command> element.
        
        >>> my_command = AdHocCommand('me@debian', id='get-registred-users-num-1', to='debian', type='set')
        >>> my_command.set_command(xmlns=NS_COMMANDS, action='execute', node='http://jabber.org/protocol/admin#get-registered-users-num').string()
        "<iq from='me@debian' to='debian' type='set' id='get-registred-users-num-1'  xml:lang='en'><command action='execute' node='http://jabber.org/protocol/admin#get-registered-users-num' xmlns='http://jabber.org/protocol/commands' /></iq>"
        """
        self.jid = jid
        self.iq_stanza = "<iq from='%s'" % self.jid
        self.iq_stanza_middle = "xml:lang='en'>"
        self.iq_end_stanza = "</iq>"
        for k, v in kwargs.iteritems():
            self.iq_stanza = "%s %s='%s'" % (self.iq_stanza, k, v)
        self.iq_stanza = "%s %s" % (self.iq_stanza, self.iq_stanza_middle) 

    def set_command(self, **kwargs):
        """
        Generate the <command> of the XML stanza.
        """
        self.command_stanza = "<command"
        self.command_end_stanza = "/>"
        for k,v in kwargs.iteritems():
            self.command_stanza = "%s %s='%s'" % (self.command_stanza, k, v)
        self.command_stanza = "%s %s" % (self.command_stanza, self.command_end_stanza)
        return self

    def string(self):
        """Returns the string version of this command"""
        return "%s%s%s" % (self.iq_stanza, self.command_stanza, self.iq_end_stanza)


class JID:
    """
    Class built for ease to use JIDs
    
    >>> my_jid = JID('me@myserver.com')
    >>> print my_jid
    me@myserver.com
    >>> print my_jid.user
    me
    >>> print my_jid.host
    myserver.com
    >>> print my_jid.full_jid
    me@myserver.com
    """
    
    def __init__(self, jid, resource):
        """
        Initialize the JID object: cut the various par of the given string
        The JID must match the following form: user@domain
        So, DON'T provide the RESOURCE!
        """
        
        val = jid.split('@')
        self.user = val[0]
        self.host = val[1]
        self.resource = resource
        self.full_jid = jid
        self.jid_with_resource = '%s/%s' % (self.full_jid, self.resource)
        
    def __str__(self):
        """String representation for ease of use. Returns the full jid."""
        return self.full_jid
        
        
if __name__ == '__main__':
    action = sys.argv[1]    
    if action == 'test':
        import doctest
        doctest.testmod()
    else:
        USERNAME = sys.argv[2]
        PASSWORD = sys.argv[3]
        SERVICE = sys.argv[4]

        if action == 'auth':
            c = BOSHClient(SERVICE, USERNAME, PASSWORD)
            c.init_connection()
            c.request_bosh_session()
            c.authenticate_xmpp()
            c.close_connection()
        elif action == 'register':
            c = BOSHClient(SERVICE, USERNAME)
            c.init_connection()
            c.request_bosh_session()
            c.register(username='moi', password='blah')
            c.close_connection()
        elif action== 'admin':
            client = AdminBOSHClient(SERVICE, jid=USERNAME, password=PASSWORD, resource='boshclient', debug=True)
            client.init_connection()
            client.request_bosh_session()
            client.authenticate_xmpp()
            client.xmpp_disco()
            client.xmpp_disco_node('admin')
            client.add_user('testme','imfamous')
            client.close_connection()            
        else:
            print 'Unknown action "%s". Please use "auth" or "register".' % action