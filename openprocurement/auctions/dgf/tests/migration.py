# -*- coding: utf-8 -*-
import unittest

from openprocurement.auctions.dgf.migration import migrate_data, get_db_schema_version, set_db_schema_version, SCHEMA_VERSION
from openprocurement.auctions.dgf.tests.base import test_auction_data, BaseWebTest


class MigrateTest(BaseWebTest):

    def setUp(self):
        super(MigrateTest, self).setUp()
        migrate_data(self.app.app.registry)

    def test_migrate(self):
        self.assertEqual(get_db_schema_version(self.db), SCHEMA_VERSION)
        migrate_data(self.app.app.registry, 1)
        self.assertEqual(get_db_schema_version(self.db), SCHEMA_VERSION)

    def test_migrate_from0to1(self):
        set_db_schema_version(self.db, 0)
        data = test_auction_data.copy()
        data['doc_type'] = "Auction"
        data['auctionID'] = "UA-X"
        _id, _rev = self.db.save(data)
        item = self.db.get(_id)
        migrate_data(self.app.app.registry, 1)
        migrated_item = self.db.get(_id)
        self.assertEqual(test_auction_data['items'][0]['quantity'], item['items'][0]['quantity'])
        self.assertEqual(unicode(test_auction_data['items'][0]['quantity']), migrated_item['items'][0]['quantity'])


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(MigrateTest))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
