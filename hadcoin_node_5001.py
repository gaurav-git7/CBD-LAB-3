# Cryptocurrency Node - Port 5001
# Run 3 nodes (5001, 5002, 5003) in separate terminals
# Use Postman to connect nodes, add transactions, mine blocks, and sync chains

# Importing the libraries
import datetime
import hashlib
import json
from flask import Flask, jsonify, request
import requests
from uuid import uuid4
from urllib.parse import urlparse

# Part 1 - Building the Blockchain

class Blockchain:

    def __init__(self):
        self.chain = []
        self.transactions = []                                                  # Mempool for pending transactions
        self.nodes = set()                                                      # Set of peer nodes in the network

    def create_block(self, proof, previous_hash, merkle_root, transactions, timestamp, block_hash):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': timestamp,
            'proof': proof,
            'previous_hash': previous_hash,
            'merkle_root': merkle_root,
            'transactions': transactions,
            'block_hash': block_hash
        }
        # Remove mined transactions from the mempool
        for tx in transactions:
            if tx in self.transactions:
                self.transactions.remove(tx)
        self.chain.append(block)
        return block

    def get_merkle_root(self, transactions):
        if not transactions:
            return '0'
        temp_transactions = [json.dumps(tx, sort_keys=True) for tx in transactions]
        while len(temp_transactions) > 1:
            if len(temp_transactions) % 2 != 0:
                temp_transactions.append(temp_transactions[-1])
            new_level = []
            for i in range(0, len(temp_transactions), 2):
                hash_val = hashlib.sha256(
                    (temp_transactions[i] + temp_transactions[i + 1]).encode()
                ).hexdigest()
                new_level.append(hash_val)
            temp_transactions = new_level
        return temp_transactions[0]

    def get_previous_block(self):
        if len(self.chain) == 0:
            return None
        return self.chain[-1]

    def proof_of_work(self, block_index, timestamp, previous_hash, merkle_root, transactions):
        tx_data = json.dumps(transactions, sort_keys=True)
        new_proof = 0
        check_proof = False
        while check_proof is False:
            hash_operation = hashlib.sha256(
                (str(new_proof) + str(block_index) + str(timestamp) + previous_hash + merkle_root + tx_data).encode()
            ).hexdigest()
            if hash_operation[:3] == '000':
                check_proof = True
            else:
                new_proof += 1
        return new_proof

    def compute_block_hash(self, block):
        """Recompute the PoW hash from block fields."""
        tx_data = json.dumps(block['transactions'], sort_keys=True)
        return hashlib.sha256(
            (str(block['proof']) + str(block['index']) + block['timestamp']
             + block['previous_hash'] + block['merkle_root'] + tx_data).encode()
        ).hexdigest()

    def is_chain_valid(self, chain):
        if len(chain) == 0:
            return True

        first_block = chain[0]
        if first_block['previous_hash'] != '0':
            return False
        if self.get_merkle_root(first_block['transactions']) != first_block['merkle_root']:
            return False
        computed_hash = self.compute_block_hash(first_block)
        if computed_hash[:3] != '000':
            return False
        if first_block['block_hash'] != computed_hash:
            return False

        previous_block = first_block
        block_index = 1
        while block_index < len(chain):
            block = chain[block_index]
            if block['previous_hash'] != previous_block['block_hash']:
                return False
            if self.get_merkle_root(block['transactions']) != block['merkle_root']:
                return False
            computed_hash = self.compute_block_hash(block)
            if computed_hash[:3] != '000':
                return False
            if block['block_hash'] != computed_hash:
                return False
            previous_block = block
            block_index += 1
        return True

    def add_transaction(self, sender, receiver, amount):
        self.transactions.append({
            'sender': sender,
            'receiver': receiver,
            'amount': amount
        })
        previous_block = self.get_previous_block()
        if previous_block is None:
            return 1
        return previous_block['index'] + 1

    def add_node(self, address):
        """Add a peer node to the network."""
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def replace_chain(self):
        """Consensus: replace current chain with the longest valid chain in the network."""
        network = self.nodes
        longest_chain = None
        max_length = len(self.chain)
        for node in network:
            try:
                response = requests.get(f'http://{node}/get_chain')
                if response.status_code == 200:
                    length = response.json()['length']
                    chain = response.json()['chain']
                    if length > max_length and self.is_chain_valid(chain):
                        max_length = length
                        longest_chain = chain
            except requests.exceptions.ConnectionError:
                continue
        if longest_chain:
            self.chain = longest_chain
            return True
        return False


# Part 2 - Flask API

app = Flask(__name__)

# Unique address for this node
node_address = str(uuid4()).replace('-', '')

# Creating the Blockchain
blockchain = Blockchain()

# Preload mempool with 5 default transactions
blockchain.add_transaction('Alice', 'Bob', 50)
blockchain.add_transaction('Bob', 'Charlie', 30)
blockchain.add_transaction('Charlie', 'Diana', 20)
blockchain.add_transaction('Diana', 'Eve', 45)
blockchain.add_transaction('Eve', 'Alice', 60)


# POST /add_transaction — Add a transaction to the mempool and broadcast to peers
@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    json_data = request.get_json()
    required_fields = ['sender', 'receiver', 'amount']
    if not json_data or not all(field in json_data for field in required_fields):
        return jsonify({'error': 'Missing fields. Required: sender, receiver, amount'}), 400
    index = blockchain.add_transaction(json_data['sender'], json_data['receiver'], json_data['amount'])

    # Broadcast the transaction to all connected peer nodes
    for node in blockchain.nodes:
        try:
            requests.post(f'http://{node}/receive_transaction', json={
                'sender': json_data['sender'],
                'receiver': json_data['receiver'],
                'amount': json_data['amount']
            }, timeout=3)
        except requests.exceptions.RequestException:
            continue  # Skip unreachable nodes

    response = {
        'message': f'This transaction will be added to Block {index} and broadcast to all peers',
        'pending_transactions': len(blockchain.transactions)
    }
    return jsonify(response), 201


# POST /receive_transaction — Internal endpoint: receive a broadcasted transaction (no re-broadcast)
# Only accepts requests from registered peer nodes
@app.route('/receive_transaction', methods=['POST'])
def receive_transaction():
    # Extract IPs of all registered peer nodes
    peer_ips = {node.split(':')[0] for node in blockchain.nodes}
    if request.remote_addr not in peer_ips:
        return jsonify({'error': 'Forbidden: only peer nodes can call this endpoint'}), 403
    json_data = request.get_json()
    required_fields = ['sender', 'receiver', 'amount']
    if not json_data or not all(field in json_data for field in required_fields):
        return jsonify({'error': 'Missing fields'}), 400
    index = blockchain.add_transaction(json_data['sender'], json_data['receiver'], json_data['amount'])
    response = {'message': f'Transaction received and added to mempool. Will be in Block {index}'}
    return jsonify(response), 201


# GET /pending_transactions — View all pending (unmined) transactions
@app.route('/pending_transactions', methods=['GET'])
def pending_transactions():
    response = {
        'pending_transactions': blockchain.transactions,
        'count': len(blockchain.transactions)
    }
    return jsonify(response), 200


# GET /mine_block — Mine a new block (requires at least 1, takes up to 5 pending transactions)
@app.route('/mine_block', methods=['GET'])
def mine_block():
    if len(blockchain.transactions) < 1:
        return jsonify({
            'error': 'No pending transactions to mine. Add at least 1 transaction first.'
        }), 400

    # Take up to 5 transactions from the mempool
    transactions_to_mine = blockchain.transactions[:5]

    # Add mining reward transaction
    blockchain.add_transaction(sender='NETWORK', receiver=node_address, amount=1)

    previous_block = blockchain.get_previous_block()
    if previous_block is None:
        previous_hash = '0'
    else:
        previous_hash = previous_block['block_hash']
    merkle_root = blockchain.get_merkle_root(transactions_to_mine)

    block_index = len(blockchain.chain) + 1
    timestamp = str(datetime.datetime.now())
    proof = blockchain.proof_of_work(block_index, timestamp, previous_hash, merkle_root, transactions_to_mine)

    tx_data = json.dumps(transactions_to_mine, sort_keys=True)
    block_hash = hashlib.sha256(
        (str(proof) + str(block_index) + timestamp + previous_hash + merkle_root + tx_data).encode()
    ).hexdigest()

    block = blockchain.create_block(proof, previous_hash, merkle_root, transactions_to_mine, timestamp, block_hash)

    # Broadcast mined transactions to all peers so they remove them from their mempools
    for node in blockchain.nodes:
        try:
            requests.post(f'http://{node}/sync_mempool', json={
                'mined_transactions': transactions_to_mine
            }, timeout=3)
        except requests.exceptions.RequestException:
            continue

    response = {
        'message': 'Congratulations, you just mined a block!',
        'index': block['index'],
        'timestamp': block['timestamp'],
        'nonce': block['proof'],
        'previous_hash': block['previous_hash'],
        'merkle_root': block['merkle_root'],
        'block_hash': block['block_hash'],
        'transactions': block['transactions']
    }
    return jsonify(response), 200


# POST /sync_mempool — Internal endpoint: remove mined transactions from this node's mempool
# Only accepts requests from registered peer nodes
@app.route('/sync_mempool', methods=['POST'])
def sync_mempool():
    peer_ips = {node.split(':')[0] for node in blockchain.nodes}
    if request.remote_addr not in peer_ips:
        return jsonify({'error': 'Forbidden: only peer nodes can call this endpoint'}), 403
    json_data = request.get_json()
    mined_transactions = json_data.get('mined_transactions', [])
    removed = 0
    for tx in mined_transactions:
        if tx in blockchain.transactions:
            blockchain.transactions.remove(tx)
            removed += 1
    response = {
        'message': f'Mempool synced. {removed} transaction(s) removed.',
        'pending_transactions': len(blockchain.transactions)
    }
    return jsonify(response), 200


# GET /get_chain — Get the full blockchain
@app.route('/get_chain', methods=['GET'])
def get_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    }
    return jsonify(response), 200


# GET /is_valid — Validate the blockchain
@app.route('/is_valid', methods=['GET'])
def is_valid():
    valid = blockchain.is_chain_valid(blockchain.chain)
    if valid:
        response = {'message': 'All good. The Blockchain is valid.'}
    else:
        response = {'message': 'Houston, we have a problem. The Blockchain is not valid.'}
    return jsonify(response), 200


# Part 3 - Decentralizing the Blockchain

# POST /connect_node — Connect peer nodes
@app.route('/connect_node', methods=['POST'])
def connect_node():
    json_data = request.get_json()
    nodes = json_data.get('nodes')
    if nodes is None:
        return jsonify({'error': 'No node provided'}), 400
    for node in nodes:
        blockchain.add_node(node)
    response = {
        'message': 'All the nodes are now connected. The Blockchain network contains the following nodes:',
        'total_nodes': list(blockchain.nodes)
    }
    return jsonify(response), 201


# GET /replace_chain — Consensus: replace chain with the longest valid one
@app.route('/replace_chain', methods=['GET'])
def replace_chain():
    is_chain_replaced = blockchain.replace_chain()
    if is_chain_replaced:
        response = {
            'message': 'The nodes had different chains so the chain was replaced by the longest one.',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'All good. The chain is the largest one.',
            'actual_chain': blockchain.chain
        }
    return jsonify(response), 200


# Running the app on port 5001
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
