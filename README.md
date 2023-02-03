# synapse-sinkdb
Synapse Rapid Powerup for [SinkDB](https://sinkdb.abuse.ch/)

## Install

To install the latest release, run the following Storm command

```
storm> pkg.load --raw https://github.com/captainGeech42/synapse-sinkdb/releases/latest/download/synapse_sinkdb.json
```

You can also clone this repo, and install via the telepath API:

```
$ python -m synapse.tools.genpkg --push aha://mycortex synapse-sinkdb.yaml
```

## Usage

First, configure your HTTPS API key (globally, or per user with `--self`):

```
storm> zw.sinkdb.setup.apikey <api key here>
```

Then, you can lookup IOCs against SinkDB

```
storm> inet:fqdn=mysinkhole.net | zw.sinkdb.lookup
```

For more details, please run `help zw.sinkdb`.

## Running the test suite

You must have a SinKDB HTTPS API key to run the tests. Please put the key in `$SYNAPSE_SINKDB_APIKEY` when running the tests.

Additionally, you must provide your own entries on SinkDB, since the data is TLP:AMBER and can't be stored in the public test code. Test data should be a JSON blob in the following structure (`ipv6_range` may be left empty currently, but should still be present):

```
{
    "ipv4": [],
    "ipv6": [],
    "ipv4_range": [],
    "ipv6_range": [],
    "domain_soa": [],
    "whois_email": [],
    "nameserver": []
}
```

This can be stored on disk and provided as a filepath in `$SYNAPSE_SINKDB_DATA_PATH`, or the data can be stored directly in `$SYNAPSE_SINKDB_DATA`. Optionally, if you can verify SinkDB access to me, I'll send you my test blob to make things easier for you.

```
$ pip install -r requirements.txt
$ SYNAPSE_SINKDB_APIKEY=asdf SYNAPSE_SINKDB_DATA_PATH=sinkdb_data.json python -m pytest test_synapse_sinkdb.py
```