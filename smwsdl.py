# This module provides support for HP ServiceManager Web Services (WSDL)
# $Id$

# The following constants are the tested modules.

INCIDENT = "incident"
version = '$Revision$'

import ConfigParser, os, string
import logging
from optparse import OptionParser
from optparse import OptionGroup
import sys

# This program requires the python SUDS package. If the import in the
# next line fails, then try
# - sudo apt-get install python-setuptools  or yum install python-setuptools
# - sudo easy_install http://pypi.python.org/packages/2.6/s/suds/suds-0.4-py2.6.egg
from suds import WebFault
from suds.client import Client
from suds.transport.http import HttpAuthenticated

logging.basicConfig(level=logging.ERROR)

######################################################################

def camel2unix(x):
    """A convenience function when you want to go from SomethingCamelCase to something-camel-case"""
    answer = x[0].lower()
    for i in range(1,len(x)-1):
        answer = answer + x[i].lower()
        if x[i].islower() and x[i+1].isupper():
            answer = answer + '-'
        if (i+2<len(x)) and x[i].isupper() and x[i+1].isupper() and x[i+2].islower():
            answer = answer + '-'
    answer = answer + x[-1].lower()
    return answer


######################################################################


wsdl_paths = { INCIDENT : "IncidentManagement.wsdl" }

class smwsdl:
    """Reads config files from /etc/smwsdl.cfg, ~/.smswsdl.cfg,
./.smswsdl.cfg and $SMWSDL_CONF. Figures out which server to connect
to."""
    def __init__(self,sm_module):
        self.__sm_module = sm_module
        self.__wsdl_path = wsdl_paths[sm_module]

        self.__read_config()
        self.__deduce_defaults_section()
        self.__get_connection_details()
        self.__create_soap_client()

    def print_available_methods(self):
        print self.__client

    def add_to_command_line_parser(self,parser,soap_data_type,include_keys=True,include_instance=True,provide_defaults=False):
        """Given a SOAP data type, returns an OptionParser which
        parses command-lines based on the WSDL service. e.g. if
        AffectedCI is part of the soap_data_type, returns a parser
        which understands --affected-ci=....
        """
        modelthing = self.__client.factory.create(soap_data_type)
        ticket_fields = []
        if include_keys:
            ticket_fields = ticket_fields + dir(modelthing.keys)
            key_group = parser
        if include_instance:
            ticket_fields = ticket_fields + dir(modelthing.instance)
            instance_group = parser
        if include_keys and include_instance:
            key_group = OptionGroup(parser,"Key/Search/Selection options")
            parser.add_option_group(key_group)
            instance_group = OptionGroup(parser,"Update/create options")
            parser.add_option_group(instance_group)
        ticket_fields = filter(lambda x: x[0:1]!='_',ticket_fields)
        seen = {}
        for field in ticket_fields:
            if seen.has_key(field): continue
            seen[field]=True
            # read the config file and see if there are any defaults
            if provide_defaults:
                if self.__config.has_option(self.__default_section,field):
                    def_value = self.__config.get(self.__default_section,field)
                    parser.set_default(field,def_value)
                    helptext = "Set the "+field+" field (default='%default')"
                else:
                    helptext = "Set the "+field+" field (no default)"
            else:
                helptext = "The "+field+" field."
            unixified = camel2unix(field)
            if modelthing.keys.__dict__.has_key(field) and include_keys:
                group = key_group
            elif modelthing.instance.__dict__.has_key(field) and include_instance:
                group = instance_group
            else:
                group = parser
            group.add_option("--"+unixified,dest=field,type='string',
                              action="store",help=helptext)


        # To-do. It should also iterate of modelthing.keys, and put them
        # into a separate option group. We should have an argument to say
        # whether we are creating or doing some kind of update.


    def create_soap_object(self,soap_data_type,initialisation_dict):
        modelthing = self.__client.factory.create(soap_data_type)
        for field in initialisation_dict.keys():
            if modelthing.keys.__dict__.has_key(field):
                modelthing.keys.__dict__[field] = initialisation_dict[field]
            elif modelthing.instance.__dict__.has_key(field):
                modelthing.instance.__dict__[field] = initialisation_dict[field]
            # And skip it otherwise. It's probably irrelevant.
            # Maybe I should warn?

        return modelthing

    def invoke(self,function,argument):
        func = self.__client.service.__getattr__(function)
        return func(argument)

    def __deduce_defaults_section(self):
        best_environment = "SMWSDL_" + self.__sm_module.upper() + "_DEFAULTS"
        if os.environ.has_key(best_environment):
            self.__default_section = os.environ[best_environment]
            return
        if os.environ.has_key('SMWSDL_DEFAULTS'):
            self.__default_section = os.environ['SMWSDL_DEFAULTS']
            return
        self.__default_section = self.__sm_module + " defaults"

    def __read_config(self):
        config_file_locations = ['/etc/smswsdl.conf',
                                 os.path.expanduser('~/.smwsdl.cfg'),
                                 '.smwsdl.cfg'
                                 ]
        if os.environ.has_key('SMWSDL_CONF'):
            config_file_locations.append(os.environ['SMWSDL_CONF'])

        self.__config = ConfigParser.ConfigParser()
        files_read = self.__config.read(config_file_locations)
        if files_read == []:
            sys.exit("Cannot continue because none of the following files were usable: "+string.join(config_file_locations," "))


    def __get_connection_details(self):
        """Read the [connection] section from the config file"""
        if self.__config.has_option('connection','server'):
            self.__service_manager_server = self.__config.get('connection','server')
        else:
            sys.exit("Server not specified")

        if self.__config.has_option('connection','protocol'):
            self.__service_manager_protocol = self.__config.get('connection','protocol')
        else:
            self.__service_manager_protocol = 'http'

        if self.__config.has_option('connection','port'):
            self.__service_manager_port = self.__config.getint('connection','port')
        else:
            self.__service_manager_port = 13080
    
        if self.__config.has_option('connection','password'):
            self.__service_manager_password = self.__config.get('connection','password')
        elif self.__config.has_option('connection','pass'):
            self.__service_manager_password = self.__config.get('connection','pass')
        else:
            self.__service_manager_password = ''

        if self.__config.has_option('connection','username'):
            self.__service_manager_username = self.__config.get('connection','username')
        elif self.__config.has_option('connection','user'):
            self.__service_manager_username = self.__config.get('connection','user')
        else:
            sys.exit("Username not specified")


    def __create_soap_client(self):
        url = self.__service_manager_protocol + "://" + self.__service_manager_server + ":" + `self.__service_manager_port` + "/SM/7/" + self.__wsdl_path
        t = HttpAuthenticated(username=self.__service_manager_username,
                              password=self.__service_manager_password)
        self.__client = Client(url,transport=t)

                      


def typical_update_program(sm_module,search_arg_type,invocation,uses_values=True):
    web_service = smwsdl(sm_module)
    parser = OptionParser(usage="usage: %prog --"+sm_module+"-id=...",version=version)
    web_service.add_to_command_line_parser(parser,search_arg_type,include_instance=uses_values)
    (options,args) = parser.parse_args()
    new_incident = web_service.create_soap_object(search_arg_type,options.__dict__)
    answer = web_service.invoke(invocation,new_incident)
    for m in answer.messages.message:
        sys.stderr.write(m.value+'\n')


def typical_create_program(sm_module,creation_arg_type,invocation,return_part):
    web_service = smwsdl(sm_module)
    parser = OptionParser(usage="usage: %prog --field-name=Value ...",
                          version=version)
    web_service.add_to_command_line_parser(parser,creation_arg_type,
                                           include_keys=False,
                                           provide_defaults=True)
    (options,args) = parser.parse_args()
    new_incident = web_service.create_soap_object(creation_arg_type,options.__dict__)
    answer = web_service.invoke(invocation,new_incident)
    for m in answer.messages.message:
        sys.stderr.write(m.value + "\n")
    print answer.model.instance.__dict__[return_part].value


def typical_search_program(sm_module,creation_arg_type,invocation,return_part):
    web_service = smwsdl(sm_module)
    parser = OptionParser(usage="usage: %prog --field=... --other-field=...",
                          version=version)
    web_service.add_to_command_line_parser(parser,creation_arg_type,
                                           include_keys=False,
                                           provide_defaults=False)
    (options,args) = parser.parse_args()
    new_incident = web_service.create_soap_object(creation_arg_type,options.__dict__)
    answer = web_service.invoke(invocation,new_incident)
    
    for k in answer.keys:
        print k.__dict__[return_part].value
