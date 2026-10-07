import requests, re, collections, urllib.parse, datetime, email.utils, time
UA={'User-Agent':'Mozilla/5.0 (compatible; king-probe/1.0)'}
out=[]
def log(s): print(s); out.append(s)
for q in ['キオクシア','東京エレクトロン','アドバンテスト','マイクロン']:
    url='https://news.google.com/rss/search?q=%s+when:14d&hl=ja&gl=JP&ceid=JP:ja'%urllib.parse.quote(q)
    try:
        r=requests.get(url,headers=UA,timeout=30)
        log('GNEWS %s HTTP %s bytes %d'%(q,r.status_code,len(r.content)))
        items=re.findall(r'<item>(.*?)</item>',r.text,flags=re.S)
        c=collections.Counter()
        for it in items:
            m=re.search(r'<pubDate>(.*?)</pubDate>',it)
            if m: c[email.utils.parsedate_to_datetime(m.group(1)).astimezone(datetime.timezone(datetime.timedelta(hours=9))).date().isoformat()]+=1
        log('  items=%d perday=%s'%(len(items),sorted(c.items())))
        t=re.search(r'<title>(.*?)</title>',items[0]) if items else None
        log('  first=%s'%(t.group(1) if t else None))
    except Exception as e: log('GNEWS %s ERR %r'%(q,e))
    time.sleep(1)
for q in ['Kioxia','"Tokyo Electron"','Advantest','Micron']:
    url='https://api.gdeltproject.org/api/v2/doc/doc?query=%s&mode=timelinevol&timespan=14d&format=json'%urllib.parse.quote(q)
    try:
        r=requests.get(url,headers=UA,timeout=40)
        log('GDELT %s HTTP %s bytes %d'%(q,r.status_code,len(r.content)))
        log('  '+r.text[:300].replace('\n',' '))
    except Exception as e: log('GDELT %s ERR %r'%(q,e))
    time.sleep(6)
open('data/news_probe.txt','w',encoding='utf-8').write('\n'.join(out)+'\n')
