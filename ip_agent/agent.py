# coding=utf-8
import requests
from bs4 import BeautifulSoup
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import ConfigParser
import sys
from datetime import datetime
import time
import json
from random import choice

cf = ConfigParser.ConfigParser()
cf.read('config.ini')
DATABASE_URI = cf.get('param', 'sql_conn')
HEART_BEAT = int(cf.get('param', 'heart_beat'))
POOL_SIZE = int(cf.get('param', 'pool_size'))
PAGE_NUM = int(cf.get('param', 'page_num'))
BaseModel = declarative_base()
engine = create_engine(DATABASE_URI, pool_recycle=3600, encoding='utf-8')
DBSession = sessionmaker(engine)


class IP(BaseModel):
    __tablename__ = 'ip'
    id = Column(Integer, primary_key=True)
    url = Column(String(35), unique=True)
    create_time = Column(DateTime)
    rank = Column(Integer)

    def to_proxy(self):
        return {'http': self.url}


def update_ip_pool(session):
    def get(i):
        valid_ip = session.query(IP).order_by(IP.rank).limit(PAGE_NUM*3).all()
        proxies = None if valid_ip == [] else choice(valid_ip).to_proxy()
        print '使用代理{}抓取第{}页'.format(proxies, i)
        try:
            req = requests.get('http://ip84.com/dl/{}'.format(page + 1), proxies=proxies, timeout=5)
        except Exception:
            req = None
        return None if req is None or req.status_code != 200 or req.content == 'block' else req.content
    run_count = 0
    print 'ip池供应不足，开始更新ip池'
    for page in range(PAGE_NUM):
        run_count += 1
        content = get(page)
        while content is None:
            content = get(page)
        html = BeautifulSoup(content, 'lxml')
        for tr in html.find_all('tr'):
            td = tr.find_all('td')
            if not td or len(td) < 5 or td[4].text != 'HTTP': continue
            url = "http://{}:{}".format(td[0].text, td[1].text)
            ip = IP(url=url, create_time=datetime.now())
            if session.query(IP).filter_by(url=url).first() is None:
                session.add(ip)
        session.commit()
        if run_count > 100: break
        time.sleep(3)


def check_and_rank_ip(session):
    valid_ip = []
    all_ip = session.query(IP).all()
    for ip in all_ip:
        t = time.time()
        try:
            print ip.to_proxy(),
            respond = requests.post('http://so.m.jd.com/ware/searchList.action',
                                    data={'_format_': 'json', 'stock': 1, 'page': 1, 'keyword': '手机'},
                                    proxies=ip.to_proxy(), timeout=5).content
            # respond = requests.get('http://nazgrim.com/{}'.format(ip.url), proxies=ip.to_proxy(), timeout=5).content
            json.loads(respond)
            print respond[:50]
            ip.rank = int(100 * (time.time() - t))
            valid_ip.append(ip)
        except Exception, e:
            print type(e)
            session.delete(ip)
        session.commit()
    return len(valid_ip)


def serve():
    while True:
        session = DBSession()
        valid_ip_count = check_and_rank_ip(session)
        if valid_ip_count < POOL_SIZE:
            update_ip_pool(session)
        session.close()
        time.sleep(HEART_BEAT)


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'initdb':
        BaseModel.metadata.create_all(engine)
    elif action == 'serve':
        serve()
