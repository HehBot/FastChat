# FireChat

FireChat - the stupid chat application

## Features implemented
 - Personal messaging
 - Group messaging
 - Chat and file-sharing
 - Everything is end-to-end encrypted
 - Load distributed among multiple servers

## Tech used
 - `rsa` and `Crypto.Cipher.AES` for encryption
 - `socket` for networking
 - `selectors` for stream management
 - `threading` for parallel sending and receiving on client-size
 - `sqlite3` for database management using SQL

## Setup
In `code` folder,
 - `./setup` to setup and start PostgreSQL server (sets password for user `postgres` to `Hello@123` and creates database `fastchat`)
 - `../test/srs localhost <port> <num>` to start `<num>` servers on localhost on ports <port> ... <port> + <num> 

## Testing
In `test` folder,
 - `./cts localhost <port> <num>` to emulate `<num>` clients connecting, interacting with each other, and disconnecting
 - `python3 find_latency.py <num>` to evaluate average latency, where `<num>` is number of clients

## Contributions
TODO
