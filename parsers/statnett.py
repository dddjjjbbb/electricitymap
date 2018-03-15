#!/usr/bin/env python3
# The arrow library is used to handle datetimes
import arrow
import logging
# The request library is used to fetch content through HTTP
import requests

# Mappings used to go from country to bidding zone level
exchanges_mapping = {
    'BY->LT': [
        'BY->LT'
    ],
    'DE->DK-DK1': [
        'DE->DK1',
    ],
    'DE->DK-DK2': [
        'DE->DK2',
    ],
    'DE->SE': [
        'DE->SE4'
    ],
    'DK-DK1->NO': [
        'DK1->NO2'
    ],
    'DK-DK1->SE': [
        'DK1->SE3'
    ],
    'DK-DK2->SE': [
        'DK2->SE4'
    ],
    'EE->RU': [
        'EE->RU'
    ],
    'EE->LV': [
        'EE->LV'
    ],
    'EE->FI': [
        'EE->FI'
    ],
    'FI->NO': [
        'FI->NO4'
    ],
    'FI->RU': [
        'FI->RU'
    ],
    'FI->SE': [
        'FI->SE1',
        'FI->SE3'
    ],
    'LT->LV': [
        'LT->LV'
    ],
    'LT->SE': [
        'LT->SE4'
    ],
    'LT->PL': [
        'LT->PL'
    ],
    'LT->RU-KGD': [
        'LT->RU'
    ],
    'LV->RU': [
        'LV->RU'
    ],
    'NL->NO': [
        'NL->NO2'
    ],
    'NO->SE': [
        'NO1->SE3',
        'NO3->SE2',
        'NO4->SE1',
        'NO4->SE2'
    ],
    'NO->RU': [
        'NO4->RU'
    ],
    'PL->SE': [
        'PL->SE4'
    ]
}


def fetch_production(zone_key='SE', session=None, target_datetime=None, logger=logging.getLogger(__name__)):
    r = session or requests.session()
    timestamp = (target_datetime.timestamp() if target_datetime else arrow.now().timestamp) * 1000
    url = 'http://driftsdata.statnett.no/restapi/ProductionConsumption/GetLatestDetailedOverview?timestamp=%d' % timestamp
    response = r.get(url)
    obj = response.json()

    data = {
        'zoneKey': zone_key,
        'production': {
            'nuclear': float(list(filter(
                lambda x: x['titleTranslationId'] == 'ProductionConsumption.%s%sDesc' % (
                'Nuclear', zone_key),
                obj['NuclearData']))[0]['value'].replace(u'\xa0', '')),
            'hydro': float(list(filter(
                lambda x: x['titleTranslationId'] == 'ProductionConsumption.%s%sDesc' % (
                'Hydro', zone_key),
                obj['HydroData']))[0]['value'].replace(u'\xa0', '')),
            'wind': float(list(filter(
                lambda x: x['titleTranslationId'] == 'ProductionConsumption.%s%sDesc' % (
                'Wind', zone_key),
                obj['WindData']))[0]['value'].replace(u'\xa0', '')),
            'unknown':
                float(list(filter(
                    lambda x: x['titleTranslationId'] == 'ProductionConsumption.%s%sDesc' % (
                    'Thermal', zone_key),
                    obj['ThermalData']))[0]['value'].replace(u'\xa0', '')) +
                float(list(filter(
                    lambda x: x['titleTranslationId'] == 'ProductionConsumption.%s%sDesc' % (
                    'NotSpecified', zone_key),
                    obj['NotSpecifiedData']))[0]['value'].replace(u'\xa0', '')),
        },
        'storage': {},
        'source': 'driftsdata.stattnet.no',
    }
    data['datetime'] = arrow.get(obj['MeasuredAt'] / 1000).datetime

    return data


def fetch_exchange_by_bidding_zone(bidding_zone1='DK1', bidding_zone2='NO2', target_datetime=None,
                                   session=None, logger=logging.getLogger(__name__)):
    # Convert bidding zone names into statnett zones
    bidding_zone_1_trimmed, bidding_zone_2_trimmed = [ x.split('-')[-1] for x in [bidding_zone1, bidding_zone2] ]
    bidding_zone_a, bidding_zone_b = sorted([bidding_zone_1_trimmed, bidding_zone_2_trimmed])
    r = session or requests.session()
    timestamp = (target_datetime.timestamp() if target_datetime else arrow.now().timestamp) * 1000
    url = 'http://driftsdata.statnett.no/restapi/PhysicalFlowMap/GetFlow?Ticks=%d' % timestamp
    response = r.get(url)
    obj = response.json()

    try:
        exchange = list(filter(
            lambda x: set([x['OutAreaElspotId'], x['InAreaElspotId']]) == set(
                [bidding_zone_a, bidding_zone_b]),
            obj))[0]
    except IndexError:
        logger.warning('no data for date {} timestamp {} url {} zone 1 {} zone 2 {}'.format(
            target_datetime, timestamp, url, bidding_zone1, bidding_zone2))
        return None

    return {
        'sortedZoneKeys': '->'.join(sorted([bidding_zone1, bidding_zone2])),
        'netFlow': exchange['Value'] if bidding_zone_a == exchange['OutAreaElspotId'] else -1 * exchange['Value'],
        'datetime': arrow.get(obj[0]['MeasureDate'] / 1000).datetime,
        'source': 'driftsdata.stattnet.no',
    }


def _fetch_exchanges_from_sorted_bidding_zones(sorted_bidding_zones, target_datetime=None,
                                               session=None, logger=None):
    zones = sorted_bidding_zones.split('->')
    return fetch_exchange_by_bidding_zone(zones[0], zones[1], target_datetime, session,
                                          logger=logger)


def _sum_of_exchanges(exchanges):
    exchange_list = list(exchanges)
    if exchange_list == [None]:
        return None
    return {
        'netFlow': sum(e['netFlow'] for e in exchange_list if e is not None),
        'datetime': exchange_list[0]['datetime'],
        'source': exchange_list[0]['source']
    }


def fetch_exchange(zone_key1='DK', zone_key2='NO', session=None, target_datetime=None,
                   logger=logging.getLogger(__name__)):
    r = session or requests.session()

    sorted_exchange = '->'.join(sorted([zone_key1, zone_key2]))
    data = _sum_of_exchanges(map(lambda e: _fetch_exchanges_from_sorted_bidding_zones(
        e, target_datetime, r, logger=logger),
                                 exchanges_mapping[sorted_exchange]))
    if not data:
        return None
    data['sortedZoneKeys'] = '->'.join(sorted([zone_key1, zone_key2]))

    return data


if __name__ == '__main__':
    """Main method, never used by the Electricity Map backend, but handy for testing."""

    print('fetch_production(SE) ->')
    print(fetch_production('SE'))
    print('fetch_exchange(NO, SE) ->')
    print(fetch_exchange('NO', 'SE'))
