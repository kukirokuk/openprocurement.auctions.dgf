# -*- coding: utf-8 -*-
import logging
from openprocurement.api.models import get_now

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1
SCHEMA_DOC = 'openprocurement_auctions_dgf_schema'
DGF_TYPES = ['dgfOtherAssets', 'dgfFinancialAssets']


def get_db_schema_version(db):
    schema_doc = db.get(SCHEMA_DOC, {"_id": SCHEMA_DOC})
    return schema_doc.get("version", SCHEMA_VERSION - 1)


def set_db_schema_version(db, version):
    schema_doc = db.get(SCHEMA_DOC, {"_id": SCHEMA_DOC})
    schema_doc["version"] = version
    db.save(schema_doc)


def migrate_data(registry, destination=None):
    if registry.settings.get('plugins') and 'auctions.dgf' not in registry.settings['plugins'].split(','):
        return
    cur_version = get_db_schema_version(registry.db)
    if cur_version == SCHEMA_VERSION:
        return cur_version
    for step in xrange(cur_version, destination or SCHEMA_VERSION):
        LOGGER.info("Migrate dgf auctions schema from {} to {}".format(step, step + 1), extra={'MESSAGE_ID': 'migrate_data'})
        migration_func = globals().get('from{}to{}'.format(step, step + 1))
        if migration_func:
            migration_func(registry)
        set_db_schema_version(registry.db, step + 1)


def from0to1(registry):
    results = registry.db.iterview('auctions/all', 2 ** 10, include_docs=True)
    docs = []
    count = 0
    for i in results:
        doc = i.doc
        if doc['procurementMethodType'] not in DGF_TYPES:
            continue
        changed = False
        for item in doc.get("items", []):
            if 'quantity' in item:
                changed = True
                item['quantity'] = unicode(item['quantity'])
        for contract in doc.get("contracts", []):
            for item in contract.get("items", []):
                if 'quantity' in item:
                    changed = True
                    item['quantity'] = unicode(item['quantity'])
        if changed:
            doc['dateModified'] = get_now().isoformat()
            docs.append(doc)
        if len(docs) >= 2 ** 7:
            registry.db.update(docs)
            count += len(docs)
            docs = []
    if docs:
        registry.db.update(docs)
        count += len(docs)
    LOGGER.info("Migrated {} objects.".format(count))
    LOGGER.info("Migration complete.")
