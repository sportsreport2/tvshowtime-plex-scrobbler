#!/usr/bin/env python
import os
import sys
import platform
import logging
import time
import threading
import ConfigParser
from optparse import OptionParser

from plex_tvst_scrobbler.tvst import Tvst
from plex_tvst_scrobbler.plex_monitor import monitor_log
from plex_tvst_scrobbler.pre_check import PLSSanity

def platform_log_directory():
    ''' Retrieves the default platform specific default log location.
        This is called if the user does not specify a log location in
        the configuration file.
        github issue https://github.com/jesseward/plex-tvst-scrobbler/issues/5
    '''

    LOG_DEFAULTS = {
        'Darwin': os.path.expanduser('~/Library/Logs/Plex Media Server.log'),
        'Linux': '/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex Media Server.log',
        'Windows': os.path.join(os.environ.get('LOCALAPPDATA', 'c:'), 'Plex Media Server/Logs/Plex Media Server.log'),
        'FreeBSD': '/usr/local/plexdata/Plex Media Server/Logs/Plex Media Server.log',
        }

    return LOG_DEFAULTS[platform.system()]


def main(config):
    ''' The main thread loop

    Args:
        config (ConfigParser obj) : user specific configuration params
    '''

    logger.info('starting log monitor thread.')
    log_watch = threading.Thread(target=monitor_log, args=(config,))
    log_watch.start()

    # main thread ended/crashed. exit.
    log_watch.join()
    sys.exit(1)

if __name__ == '__main__':

    p = OptionParser()
    p.add_option('-c', '--config', action='store', dest='config_file',
        help='The location to the configuration file.')
    p.add_option('-p', '--precheck', action='store_true', dest='precheck',
        default=False, help='Run a pre-check to ensure a correctly configured system.')
    p.add_option('-a', '--authenticate', action='store_true', dest='authenticate',
        default=False, help='Generate a new TVShow Time session key.')

    p.set_defaults(config_file=os.path.expanduser(
      '~/.config/plex-tvst-scrobbler/plex_tvst_scrobbler.conf'))

    (options, args) = p.parse_args()

    if not os.path.exists(options.config_file):
        print 'Exiting, unable to locate config file {0}. use -c to specify config target'.format(
            options.config_file)
        sys.exit(1)

    # apply defaults to *required* configuration values.
    config = ConfigParser.ConfigParser(defaults = {
        'config file location': options.config_file,
        'session': os.path.expanduser('~/.config/plex-tvst-scrobbler/session_key'),
        'plex_access_token_location': os.path.expanduser('~/.config/plex-tvst-scrobbler/plex_access_token'),
        'mediaserver_url': 'http://localhost:32400',
        'mediaserver_log_location': platform_log_directory(),
        'log_file': '/tmp/plex_tvst_scrobbler.log'
      })
    config.read(options.config_file)

    FORMAT = '%(asctime)-15s [%(process)d] [%(name)s %(funcName)s] [%(levelname)s] %(message)s'
    logging.basicConfig(filename=config.get('plex-tvst-scrobbler',
      'log_file'), format=FORMAT, level=logging.DEBUG)
    logger = logging.getLogger('main')

    # dump our configuration values to the logfile
    for key in config.items('plex-tvst-scrobbler'):
        logger.debug('config : {0} -> {1}'.format(key[0], key[1]))

    if options.precheck:
        pc = PLSSanity(config)
        pc.run()
        logger.warn('Precheck completed. Exiting.')
        sys.exit(0)

    tvst = Tvst(config)

    # if a plex token object does not exist, prompt user 
    # to authenticate to plex.tv to get a plex access token
    if (not os.path.exists(config.get('plex-tvst-scrobbler','plex_access_token_location')) or
      options.authenticate):
        logger.info('Prompting to authenticate to plex.tv.')
        result = False
        while not result:
            result = tvst.plex_auth()

    # if a valid session object does not exist, prompt user
    # to authenticate.
    if (not os.path.exists(config.get('plex-tvst-scrobbler','session')) or
      options.authenticate):
        logger.info('Prompting to authenticate to TVShow Time.')
        tvst.tvst_auth()
        print 'Please relaunch plex-tvst-scrobbler service.'
        logger.warn('Exiting application.')
        sys.exit(0)

    logger.debug('using tvshowtime.com session key={key} , st_mtime={mtime}'.format(
        key=config.get('plex-tvst-scrobbler','session'),
        mtime=time.ctime(os.path.getmtime(config.get('plex-tvst-scrobbler','session'))) ))

    m = main(config)
