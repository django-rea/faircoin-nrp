#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2011 thomasv@gitorious
#
# Faircoin Payment For Odoo - module that permits faircoin payment in a odoo website 
# Copyright (C) 2015-2016 santi@punto0.org -- FairCoop 
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import time, sys, socket, os
import threading
import urllib2
import json
import Queue
import sqlite3
import urllib
import logging

import electrum_fair
from electrum_fair import util
from electrum_fair.util import NotEnoughFunds
electrum_fair.set_verbosity(True)

import ConfigParser
config = ConfigParser.ConfigParser()
config.read("daemon.conf")

my_password = config.get('main','password')
my_host = config.get('main','host')
my_port = config.getint('main','port')

wallet_path = config.get('electrum','wallet_path')

seed = config.get('electrum','seed')
password = config.get('electrum', 'password')
network_fee = config.get('network','fee')

num = 0

stopping = False

logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(levelname)s %(message)s')

def network_fee():
    return network_fee

def do_stop(password):
    global stopping
    if password != my_password:
        return "wrong password"
    stopping = True
    logging.debug("Stopping")    
    return "ok"

def send_command(cmd, params):
    import jsonrpclib
    server = jsonrpclib.Server('http://%s:%d'%(my_host, my_port))
    try:
        f = getattr(server, cmd)
    except socket.error:
        logging.error("Can not connect to the server.")
        return 1
        
    try:
        out = f(*params)
    except socket.error:
        logging.error("Can not send the command")
        return 1

    #logging.debug("sending : %s" %json.dumps(out, indent=4))
    return 0

# get the total balance for the wallet
# Returns a tupla with 3 values: Confirmed, Unmature, Unconfirmed
def get_balance():
    return wallet.get_balance()

# get the balance for a determined address
# Returns a tupla with 3 values: Confirmed, Unmature, Unconfirmed
def get_address_balance(address):
    return wallet.get_balance([address])

#check if an address is valid
def is_valid(address):
    return cmd_wallet.validateaddress(address)

#check if an address is from the wallet
def is_mine(address):
    return wallet.is_mine(address)

#read the history of an address
def get_address_history(address):
    return wallet.get_address_history(address)

# make a transfer from an adress of the wallet 
def make_transaction_from_address(address_origin, address_end, amount):
    if not is_mine(address_origin): 
        logger.error("The address %s does not belong to this wallet" %address_origin)
        return False
    if not is_valid(address_end):
        logger.error("The address %s is not a valid faircoin address" %address_end)
        return False

    inputs = [address_origin]
    coins = wallet.get_spendable_coins(domain = inputs)
    #print coins
    amount_total = ( 1.e6 * float(amount) ) - float(network_fee)
    amount_total = int(amount_total)

    if amount_total > 0:
        output = [('address', address_end, int(amount_total))] 
    else:
        logger.error("Amount negative: %s" %(amount_total) )
        return False
    try:
        tx = wallet.make_unsigned_transaction(coins, output, change_addr=address_origin)
    except NotEnoughFunds:
	        logger.error("Not enough funds confirmed to make the transaction. %s %s %s" %wallet.get_addr_balance(address_origin))
                return False
    wallet.sign_transaction(tx, password)
    rec_tx_state, rec_tx_out = wallet.sendtx(tx)
    if rec_tx_state:
         logger.info("SUCCESS. The transaction has been broadcasted.")
         return rec_tx_out
    else:
         logger.error("Sending %s fairs to the address %s" %(amount_total, address_end ) )
         return False
         
def address_history_info(address, page = 0, items = 20):
    """Return list with info of last 20 transactions of the address history"""
    return_history = []
    history = cmd_wallet.getaddresshistory(address)
    tx_num = 0
    for i, one_transaction in enumerate(history, start = page * items):
        tx_num += 1
        if tx_num > items:
            return return_history
        raw_transaction = cmd_wallet.gettransaction(one_transaction['tx_hash'])
        info_transaction = raw_transaction.deserialize()
        return_history.append({'tx_hash': one_transaction['tx_hash'], 'tx_data': info_transaction})
    return return_history

# create new address for users or any other entity
def new_fair_address(entity_id, entity = 'generic'):
    """ Return a new address labeled or False if there's no network connection. 
    The label is for debugging proposals. It's like 'entity: id'
    We can label like "user: 213" or "user: pachamama" or "order: 67".
    """
    while network.is_connected():
        new_address = wallet.create_new_address()
        check_label = wallet.get_label(new_address)
        check_history = cmd_wallet.getaddresshistory(new_address)
        # It checks if address is labeled or has history yet, a gap limit protection. 
        # This can be removed when we have good control of gap limit.     
        if not check_label[0] and not check_history:
            wallet.set_label(new_address, entity + ': ' + str(entity_id))
            return new_address
    return False

def get_confirmations(tx):
    """Return the number of confirmations of a monitored transaction
    and the timestamp of the last confirmation (or None if not confirmed)."""
    return wallet.get_confirmations(tx)

#Check if it is connected to the electum network
def is_connected():
    return network.is_connected()

def daemon_is_up():
    return True    

if __name__ == '__main__':
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        params = sys.argv[2:]
        ret = send_command(cmd, params)
        sys.exit(ret)
    logging.debug("---------------------------------")
    logging.debug("Starting electrum...")
    out_queue = Queue.Queue()
    # start network
    c = electrum_fair.SimpleConfig({'wallet_path':wallet_path})
    daemon_socket = electrum_fair.daemon.get_daemon(c, True)
    network = electrum_fair.NetworkProxy(daemon_socket, config)
    network.start()
    n = 0
    # wait until connected
    while (network.is_connecting() and (n < 100)):
        time.sleep(0.5)
        n = n + 1

    if not network.is_connected():
        logging.error("Can not init Electrum Network. Exiting.")
        sys.exit(1)

    # create wallet
    storage = electrum_fair.WalletStorage(wallet_path)
    if not storage.file_exists:
        logging.debug("creating wallet file")
        wallet = electrum_fair.wallet.Wallet.from_seed(seed, password, storage)
    else:
        wallet = electrum_fair.wallet.Wallet(storage)

    #wallet.synchronize = lambda: None # prevent address creation by the wallet
    wallet.change_gap_limit(100)  
    wallet.start_threads(network)
    #network.register_callback('updated', on_wallet_update)

    # server thread
    from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer
    server = SimpleJSONRPCServer(( my_host, my_port))
    server.register_function(network_fee, 'network_fee')
    server.register_function(do_stop, 'stop')
    server.register_function(is_connected,'is_connected')
    server.register_function(daemon_is_up,'daemon_is_up')
    server.register_function(get_confirmations,'get_confirmations')
    server.register_function(new_fair_address,'new_fair_address')
    server.register_function(address_history_info,'address_history_info')
    server.register_function(make_transaction_from_address,'make_transaction_from_address')
    server.register_function(get_address_history,'get_address_history')
    server.register_function(is_mine,'is_mine')
    server.register_function(is_valid,'is_valid')
    server.register_function(get_address_balance,'get_address_balance')
    server.register_function(get_balance,'get_balance')  
    server.socket.settimeout(1)

    while not stopping:
        try:
            server.handle_request()
        except socket.timeout:
            continue
    
    network.stop_daemon()
    if network.is_connected():
        time.sleep(1)
