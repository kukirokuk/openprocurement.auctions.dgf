# -*- coding: utf-8 -*-
import json
import decimal
import simplejson
import couchdb.json
from couchdb import util
from logging import getLogger
from pkg_resources import get_distribution
from openprocurement.api.models import get_now, TZ
from openprocurement.api.utils import (
    upload_file as base_upload_file, get_file as base_get_file,
    DOCUMENT_BLACKLISTED_FIELDS, context_unpack,
)
from openprocurement.auctions.core.utils import (
    cleanup_bids_for_cancelled_lots, check_complaint_status,
    check_auction_status, remove_draft_bids,
)

PKG = get_distribution(__package__)
LOGGER = getLogger(PKG.project_name)


my_encode = lambda obj, dumps=simplejson.dumps: dumps(obj, allow_nan=False, ensure_ascii=False)

def my_decode(string_):
    if isinstance(string_, util.btype):
        string_ = string_.decode("utf-8")
    return json.loads(string_, parse_float=decimal.Decimal)

couchdb.json.use(decode=my_decode, encode=my_encode)


def upload_file(request, blacklisted_fields=DOCUMENT_BLACKLISTED_FIELDS):
    first_document = request.validated['documents'][0] if 'documents' in request.validated and request.validated['documents'] else None
    if 'data' in request.validated and request.validated['data']:
        document = request.validated['document']
        if document.documentType in ['virtualDataRoom', 'x_dgfAssetFamiliarization']:
            if first_document:
                for attr_name in type(first_document)._fields:
                    if attr_name not in blacklisted_fields:
                        setattr(document, attr_name, getattr(first_document, attr_name))
            if document.documentType == 'x_dgfAssetFamiliarization':
                document.format = 'offline/on-site-examination'
            return document
    return base_upload_file(request, blacklisted_fields)


def get_file(request):
    document = request.validated['document']
    if document.documentType == 'virtualDataRoom':
        request.response.status = '302 Moved Temporarily'
        request.response.location = document.url
        return document.url
    return base_get_file(request)


def check_bids(request):
    auction = request.validated['auction']
    if auction.lots:
        [setattr(i.auctionPeriod, 'startDate', None) for i in auction.lots if i.numberOfBids < 2 and i.auctionPeriod and i.auctionPeriod.startDate]
        [setattr(i, 'status', 'unsuccessful') for i in auction.lots if i.numberOfBids < 2 and i.status == 'active']
        cleanup_bids_for_cancelled_lots(auction)
        if not set([i.status for i in auction.lots]).difference(set(['unsuccessful', 'cancelled'])):
            auction.status = 'unsuccessful'
    else:
        if auction.numberOfBids < 2:
            if auction.auctionPeriod and auction.auctionPeriod.startDate:
                auction.auctionPeriod.startDate = None
            auction.status = 'unsuccessful'


def check_status(request):
    auction = request.validated['auction']
    now = get_now()
    for complaint in auction.complaints:
        check_complaint_status(request, complaint, now)
    for award in auction.awards:
        for complaint in award.complaints:
            check_complaint_status(request, complaint, now)
    if not auction.lots and auction.status == 'active.tendering' and auction.tenderPeriod.endDate <= now:
        LOGGER.info('Switched auction {} to {}'.format(auction['id'], 'active.auction'),
                    extra=context_unpack(request, {'MESSAGE_ID': 'switched_auction_active.auction'}))
        auction.status = 'active.auction'
        remove_draft_bids(request)
        check_bids(request)
        if auction.numberOfBids < 2 and auction.auctionPeriod:
            auction.auctionPeriod.startDate = None
        return
    elif auction.lots and auction.status == 'active.tendering' and auction.tenderPeriod.endDate <= now:
        LOGGER.info('Switched auction {} to {}'.format(auction['id'], 'active.auction'),
                    extra=context_unpack(request, {'MESSAGE_ID': 'switched_auction_active.auction'}))
        auction.status = 'active.auction'
        remove_draft_bids(request)
        check_bids(request)
        [setattr(i.auctionPeriod, 'startDate', None) for i in auction.lots if i.numberOfBids < 2 and i.auctionPeriod]
        return
    elif not auction.lots and auction.status == 'active.awarded':
        standStillEnds = [
            a.complaintPeriod.endDate.astimezone(TZ)
            for a in auction.awards
            if a.complaintPeriod.endDate
        ]
        if not standStillEnds:
            return
        standStillEnd = max(standStillEnds)
        if standStillEnd <= now:
            check_auction_status(request)
    elif auction.lots and auction.status in ['active.qualification', 'active.awarded']:
        if any([i['status'] in auction.block_complaint_status and i.relatedLot is None for i in auction.complaints]):
            return
        for lot in auction.lots:
            if lot['status'] != 'active':
                continue
            lot_awards = [i for i in auction.awards if i.lotID == lot.id]
            standStillEnds = [
                a.complaintPeriod.endDate.astimezone(TZ)
                for a in lot_awards
                if a.complaintPeriod.endDate
            ]
            if not standStillEnds:
                continue
            standStillEnd = max(standStillEnds)
            if standStillEnd <= now:
                check_auction_status(request)
                return
