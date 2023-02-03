import asyncio
import binascii
import hashlib
import json
import os
import logging

import synapse.common as s_common
import synapse.cortex as s_cortex
import synapse.tests.utils as s_test
import synapse.tools.genpkg as s_genpkg

logger = logging.getLogger(__name__)

dirname = os.path.dirname(__file__)
pkgproto = s_common.genpath(dirname, "synapse-sinkdb.yaml")

def get_api_key() -> str | None:
    """Get the SinkDB API key."""

    return os.getenv("SYNAPSE_SINKDB_APIKEY")

def get_seed_nodes() -> dict | None:
    """Get the SinkDB seed data, either from disk or from an env var directly."""

    j = {}

    path = os.getenv("SYNAPSE_SINKDB_DATA_PATH")
    if path:
        with open(path, "r") as f:
            logger.warning("got sinkdb data from %s", path)
            j = json.loads(f.read())
    else:
        data = os.getenv("SYNAPSE_SINKDB_DATA")
        if data is None:
            logger.error("failed to find sinkdb seed data!")
            return None
        logger.warning("got sinkdb data from $SYNAPSE_SINKDB_DATA")
        j = json.loads(data)

    # make sure the dictionary has the required keys
    # TODO: find ipv6_range example
    # req_keys = ["ipv4", "ipv6", "ipv4_range", "ipv6_range", "domain_soa", "whois_email", "nameserver"]
    req_keys = ["ipv4", "ipv6", "ipv4_range", "domain_soa", "whois_email", "nameserver"]
    for k in req_keys:
        v = j.get(k, None)
        if v is None or type(v) is not list or len(v) == 0:
            logger.error("invalid structure for sinkdb data, see README.md")
            return None
    
    return j

class SynapseSinkdbTest(s_test.SynTest):

    def has_tag(self, node, tag):
        self.true(node.tags.get(tag) is not None)
    
    def not_has_tag(self, node, tag):
        self.true(node.tags.get(tag) is None)

    async def _t_install_pkg(self, core: s_cortex.Cortex):
        """Install and configure the Storm package."""

        # get API key
        api_key = get_api_key()
        self.assertIsNotNone(api_key, "You must provide an API key in $SYNAPSE_SINKDB_APIKEY to run the test suite")

        # install package
        await s_genpkg.main((pkgproto, "--push", f"cell://{core.dirn}"))

        # set the api key
        msgs = await core.stormlist("zw.sinkdb.setup.apikey --self $key", opts={"vars": {"key": api_key}})
        self.stormIsInPrint("for the current user", msgs)
            
        msgs = await core.stormlist("zw.sinkdb.setup.apikey $key", opts={"vars": {"key": api_key}})
        self.stormIsInPrint("for all users", msgs)
    
    async def _t_seed_cortex(self, core: s_cortex.Cortex):
        """Add the SinkDB test nodes to the cortex."""

        data = get_seed_nodes()
        self.assertIsNotNone(data, "You must provide seed data present in SinkDB to run the test suite. See README.md for details")

        self.assertGreater(await core.count("for $v in $vals { [inet:fqdn=$v +#test.domain_soa] }", opts={"vars": {"vals": data["domain_soa"]}}), 0)
        self.assertGreater(await core.count("for $v in $vals { [inet:fqdn=$v +#test.nameserver] }", opts={"vars": {"vals": data["nameserver"]}}), 0)
        self.assertGreater(await core.count("for $v in $vals { [inet:ipv4=$v +#test.ipv4] }", opts={"vars": {"vals": data["ipv4"]}}), 0)
        self.assertGreater(await core.count("for $v in $vals { [it:network=(test,sinkdb,$v) :net4=$v +#test.ipv4_range] }", opts={"vars": {"vals": data["ipv4_range"]}}), 0)
        self.assertGreater(await core.count("for $v in $vals { [inet:ipv6=$v +#test.ipv6] }", opts={"vars": {"vals": data["ipv6"]}}), 0)
        self.assertGreaterEqual(await core.count("for $v in $vals { [it:network=(test,sinkdb,$v) :net6=$v +#test.ipv6_range] }", opts={"vars": {"vals": data.get("ipv6_range", [])}}), 0) # TODO: flip this to assertGreater when an ipv6_range test value is identified
        self.assertGreater(await core.count("for $v in $vals { [inet:email=$v +#test.whois_email] }", opts={"vars": {"vals": data["whois_email"]}}), 0)
        self.assertGreater(await core.count("#test"), 0)
    
    async def test_synapse_sinkdb(self):
        # this test suite requires internet access
        self.skipIfNoInternet()

        async with self.getTestCore() as core:
            await self._t_install_pkg(core)
            await self._t_seed_cortex(core)