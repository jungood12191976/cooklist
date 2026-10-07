import requests, json, datetime
H={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36','Accept':'application/json, text/plain, */*','Origin':'https://www.nasdaq.com','Referer':'https://www.nasdaq.com/'}
out=[]
def log(s): print(s); out.append(s)
for d in ['2026-10-15','2026-10-22','2026-10-28']:
    try:
        r=requests.get('https://api.nasdaq.com/api/calendar/earnings?date='+d,headers=H,timeout=30)
        log('NASDAQ %s HTTP %s bytes %d'%(d,r.status_code,len(r.content)))
        try:
            j=r.json(); rows=((j.get('data') or {}).get('rows')) or []
            log('  rows=%d keys=%s'%(len(rows), list(rows[0].keys()) if rows else None))
            for row in rows:
                if row.get('symbol') in ('MU','NVDA','TSM','AVGO','AMAT','LRCX','KLAC','AMD','ASML','MSFT','GOOGL','AMZN','META','TXN','INTC','QCOM'):
                    log('  '+json.dumps(row,ensure_ascii=False))
        except Exception as e: log('  parse err %r %s'%(e,r.text[:200]))
    except Exception as e: log('NASDAQ %s ERR %r'%(d,e))
open('data/us_probe.txt','w',encoding='utf-8').write('\n'.join(out)+'\n')
