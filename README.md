# Badgyver Rust server maps

Reads the map every Rust server on the [Badgyver Rust server list](https://badgyver.com/servers/) publishes about itself, so the list can show each server's real map.

Every 15 minutes a GitHub Actions job takes the listed servers from `https://badgyver.com/wp-json/bgrs/v1/targets`, asks each one for its rules (Valve's A2S query) and writes to [`data/servers.json`](data/servers.json):

- the map picture Facepunch hosts for the server, its seed and size, and the map download;
- the server's own description, header image, logo and website.

badgyver.com reads that file. Nothing here needs a password or a key: the job only reads public server information, and only this repository's owner can change the file.
