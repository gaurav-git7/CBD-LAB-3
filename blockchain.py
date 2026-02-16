# Blockchain with Transactions, Merkle Root & Flask API
# Test with Postman at http://localhost:5000

# Importing the libraries
import datetime
import hashlib
import json
from flask import Flask, jsonify, request

# Part 1 - Building a Blockchain

class Blockchain:

    def __init__(self):
        self.chain = []
        self.transactions = []  # Mempool for pending transactions

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
        self.chain.append(block)
        return block

    def get_merkle_root(self, transactions):
        if not transactions:
            return '0'

        # Hash each transaction as a JSON string
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

        # Validate first block: previous_hash must be '0'
        first_block = chain[0]
        if first_block['previous_hash'] != '0':
            return False
        if self.get_merkle_root(first_block['transactions']) != first_block['merkle_root']:
            return False
        # Verify PoW of first block
        computed_hash = self.compute_block_hash(first_block)
        if computed_hash[:3] != '000':
            return False
        if first_block['block_hash'] != computed_hash:
            return False

        previous_block = first_block
        block_index = 1
        while block_index < len(chain):
            block = chain[block_index]

            # Verify previous hash link matches previous block's block_hash
            if block['previous_hash'] != previous_block['block_hash']:
                return False

            # Verify Merkle Root
            if self.get_merkle_root(block['transactions']) != block['merkle_root']:
                return False

            # Verify Proof of Work and stored block_hash
            computed_hash = self.compute_block_hash(block)
            if computed_hash[:3] != '000':
                return False
            if block['block_hash'] != computed_hash:
                return False

            previous_block = block
            block_index += 1
        return True

    def create_transaction(self, sender, receiver, amount):
        self.transactions.append({
            'sender': sender,
            'receiver': receiver,
            'amount': amount
        })
        previous_block = self.get_previous_block()
        if previous_block is None:
            return 1
        return previous_block['index'] + 1


# Part 2 - Flask API

app = Flask(__name__)

# Creating a Blockchain
blockchain = Blockchain()

# Preload mempool with 5 default transactions
blockchain.create_transaction('Alice', 'Bob', 50)
blockchain.create_transaction('Bob', 'Charlie', 30)
blockchain.create_transaction('Charlie', 'Diana', 20)
blockchain.create_transaction('Diana', 'Eve', 45)
blockchain.create_transaction('Eve', 'Alice', 60)


# POST /add_transaction  — Add a transaction to the mempool
# Body (JSON): { "sender": "Alice", "receiver": "Bob", "amount": 100 }
@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    json_data = request.get_json()
    required_fields = ['sender', 'receiver', 'amount']
    if not json_data or not all(field in json_data for field in required_fields):
        return jsonify({'error': 'Missing fields. Required: sender, receiver, amount'}), 400

    blockchain.create_transaction(
        sender=json_data['sender'],
        receiver=json_data['receiver'],
        amount=json_data['amount']
    )
    response = {
        'message': 'Transaction added to mempool',
        'pending_transactions': len(blockchain.transactions)
    }
    return jsonify(response), 201


# GET /pending_transactions  — View all pending (unmined) transactions
@app.route('/pending_transactions', methods=['GET'])
def pending_transactions():
    response = {
        'pending_transactions': blockchain.transactions,
        'count': len(blockchain.transactions)
    }
    return jsonify(response), 200


# GET /mine_block  — Mine a new block (requires at least 5 pending transactions)
@app.route('/mine_block', methods=['GET'])
def mine_block():
    if len(blockchain.transactions) < 5:
        return jsonify({
            'error': f'Not enough transactions to mine (min 5). Current: {len(blockchain.transactions)}'
        }), 400

    # Take first 5 transactions from the mempool
    transactions_to_mine = blockchain.transactions[:5]
    blockchain.transactions = blockchain.transactions[5:]

    previous_block = blockchain.get_previous_block()
    if previous_block is None:
        previous_hash = '0'  # First block in the chain
    else:
        previous_hash = previous_block['block_hash']
    merkle_root = blockchain.get_merkle_root(transactions_to_mine)

    block_index = len(blockchain.chain) + 1
    timestamp = str(datetime.datetime.now())
    proof = blockchain.proof_of_work(block_index, timestamp, previous_hash, merkle_root, transactions_to_mine)

    # Compute the PoW block hash (starts with '000')
    tx_data = json.dumps(transactions_to_mine, sort_keys=True)
    block_hash = hashlib.sha256(
        (str(proof) + str(block_index) + timestamp + previous_hash + merkle_root + tx_data).encode()
    ).hexdigest()

    block = blockchain.create_block(proof, previous_hash, merkle_root, transactions_to_mine, timestamp, block_hash)

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


# GET /get_chain  — Get the full blockchain
@app.route('/get_chain', methods=['GET'])
def get_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    }
    return jsonify(response), 200


# GET /is_valid  — Validate the blockchain
@app.route('/is_valid', methods=['GET'])
def is_valid():
    valid = blockchain.is_chain_valid(blockchain.chain)
    if valid:
        response = {'message': 'All good. The Blockchain is valid.'}
    else:
        response = {'message': 'Houston, we have a problem. The Blockchain is not valid.'}
    return jsonify(response), 200


# Running the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
