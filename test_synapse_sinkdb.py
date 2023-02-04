import os
import re
import json
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
    req_keys = ["ipv4", "ipv4_range", "domain_soa", "whois_email", "nameserver"]
    for k in req_keys:
        v = j.get(k, None)
        if v is None or type(v) is not list or len(v) == 0:
            logger.error("invalid structure for sinkdb data, see README.md")
            return None

    return j

class SynapseSinkdbTest(s_test.SynTest):
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
        self.assertGreater(await core.count("for $v in $vals { [inet:ipv4=$v +#test.ipv4] }", opts={"vars": {"vals": data["ipv4"]}}), 0)
        self.assertGreater(await core.count("for $v in $vals { [inet:ipv4=$v +#test.ipv4_range] }", opts={"vars": {"vals": data["ipv4_range"]}}), 0)
        self.assertGreater(await core.count("for $v in $vals { [inet:fqdn=$v +#test.nameserver] }", opts={"vars": {"vals": data["nameserver"]}}), 0)
        self.assertGreater(await core.count("for $v in $vals { [inet:email=$v +#test.whois_email] }", opts={"vars": {"vals": data["whois_email"]}}), 0)
        self.assertGreater(await core.count("#test"), 0)

    async def _t_check_lookup_type(self, core: s_cortex.Cortex, type: str, expected_tags: list[str], prefix = "rep.sinkdb"):
        """Validate a type of lookup nodes on SinkDB data modeling."""

        # get the number of nodes of the category
        num_nodes = await core.count(f"#test.{type}")
        self.assertGreater(num_nodes, 0)

        # model the sinkdb data
        msgs = await core.stormlist(f"#test.{type} | zw.sinkdb.lookup")
        self.stormHasNoWarnErr(msgs)

        # make sure each node got at least something from sinkdb
        self.assertEqual(await core.count(f"#test.{type} +#{prefix}" + " +{ <(seen)- meta:source:name=sinkdb }"), num_nodes)

        # make sure the main test node got all of the proper tags
        tag_str = " ".join([f"+#{prefix}." + x for x in expected_tags])
        self.assertGreater(await core.count(f"#test.{type} {tag_str}"), 0)

    async def test_lookups(self):
        self.skipIfNoInternet()

        async with self.getTestCore() as core:
            await self._t_install_pkg(core)
            await self._t_seed_cortex(core)

            await self._t_check_lookup_type(core, "domain_soa", ["class.listed", "expose.vendor", "has_operator", "sinkhole", "type.domain_soa"])
            await self._t_check_lookup_type(core, "ipv4", ["class.listed", "expose.vendor", "has_operator", "sinkhole", "type.ipv4"])
            await self._t_check_lookup_type(core, "ipv4_range", ["class.listed", "sinkhole", "type.ipv4_range"])
            await self._t_check_lookup_type(core, "nameserver", ["class.query_only", "has_operator", "sinkhole", "type.nameserver"])
            await self._t_check_lookup_type(core, "whois_email", ["class.listed", "has_operator", "sinkhole", "type.domain_soa", "type.whois_email"])

            msgs = await core.stormlist("[it:dev:str=asdf] | zw.sinkdb.lookup --debug")
            self.stormIsInWarn("unsupported form received", msgs)

    async def test_tag_prefix(self):
        self.skipIfNoInternet()

        async with self.getTestCore() as core:
            await self._t_install_pkg(core)
            await self._t_seed_cortex(core)

            await self._t_check_lookup_type(core, "domain_soa", ["class.listed", "expose.vendor", "has_operator", "sinkhole", "type.domain_soa"])
            msgs = await core.stormlist("zw.sinkdb.setup.tagprefix new.asdf")
            self.stormIsInPrint("tag prefix to #new.asdf", msgs)
            await self._t_check_lookup_type(core, "domain_soa", ["class.listed", "expose.vendor", "has_operator", "sinkhole", "type.domain_soa"], prefix="new.asdf")

    async def test_cache(self):
        self.skipIfNoInternet()

        async with self.getTestCore() as core:
            await self._t_install_pkg(core)
            await self._t_seed_cortex(core)

            msgs = await core.stormlist("#test.nameserver | zw.sinkdb.lookup --debug")
            self.stormIsInPrint("wrote http query cache data", msgs)
            self.stormHasNoWarnErr(msgs)
            
            msgs = await core.stormlist("#test.nameserver | zw.sinkdb.lookup --debug")
            self.stormIsInPrint("using cached data for http query", msgs)
            self.stormHasNoWarnErr(msgs)
            
            msgs = await core.stormlist("#test.nameserver | zw.sinkdb.lookup --debug --asof now")
            self.stormIsInPrint("wrote http query cache data", msgs)
            self.stormHasNoWarnErr(msgs)

    async def test_import(self):
        self.skipIfNoInternet()
        
        async with self.getTestCore() as core:
            await self._t_install_pkg(core)

            msgs = await core.stormlist("zw.sinkdb.import --debug --no-awareness --no-scanners --no-sinkholes")
            self.stormIsInWarn("no categories of sinkdb data enabled for import", msgs)
            self.stormNotInPrint("fetching", msgs)

            msgs = await core.stormlist("zw.sinkdb.import --debug --no-awareness --no-scanners")
            self.stormIsInPrint("records from sinkdb", msgs)
            self.stormIsInPrint("fetching sinkhole indicators", msgs)
            self.stormNotInPrint("fetching awareness indicators", msgs)
            self.stormNotInPrint("fetching scanner indicators", msgs)
            self.stormHasNoWarnErr(msgs)

            msgs = await core.stormlist("zw.sinkdb.import --debug --no-awareness --no-sinkholes")
            self.stormIsInPrint("records from sinkdb", msgs)
            self.stormNotInPrint("fetching sinkhole indicators", msgs)
            self.stormNotInPrint("fetching awareness indicators", msgs)
            self.stormIsInPrint("fetching scanner indicators", msgs)
            self.stormHasNoWarnErr(msgs)

            msgs = await core.stormlist("zw.sinkdb.import --debug --no-scanners --no-sinkholes")
            self.stormIsInPrint("records from sinkdb", msgs)
            self.stormNotInPrint("fetching sinkhole indicators", msgs)
            self.stormIsInPrint("fetching awareness indicators", msgs)
            self.stormNotInPrint("fetching scanner indicators", msgs)
            self.stormHasNoWarnErr(msgs)
            
            msgs = await core.stormlist("zw.sinkdb.import")
            self.stormHasNoWarnErr(msgs)
            print_str = '\n'.join([m[1].get('mesg') for m in msgs if m[0] == 'print'])
            matches = re.findall(r"modeling (\d+) records from sinkdb", print_str)
            self.assertEqual(len(matches), 1)
            self.assertGreater(int(matches[0]), 300)

            self.assertGreater(await core.count("zw.sinkdb.import --yield"), 700)

            self.assertGreater(await core.count("inet:ipv4 +#rep.sinkdb.type.ipv4_range"), 0)

            self.assertGreater(await core.count("inet:ipv4 +#rep.sinkdb +{<(has)- ps:contact +#rep.sinkdb.operator +:type=zw.sinkdb.operator}"), 0)