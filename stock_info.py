#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

"""
@File    : stock_info.py
@Author  : Gan Yuyang
@Time    : 2023/3/27 18:09
"""
import os.path
import random
import re
import time
from datetime import datetime
from functools import lru_cache
import bs4
import numpy as np
import pandas as pd
from akshare.stock.cons import hk_js_decode
from py_mini_racer import py_mini_racer
from tqdm.contrib import tzip
import heapq
from fake_useragent import UserAgent

pd.set_option('display.max_rows', 1000)
pd.set_option('display.max_columns', 1000)
import requests
import json
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from akshare import stock_zh_a_hist
# import akshare as ak
from tqdm import *
import args

from pyecharts import options as opts
from pyecharts.charts import Map, Page, Bar, Line, Kline, Grid
from pyecharts.commons.utils import JsCode


def code2cn_name(code: str):
    if str(code)[0] == '6':
        rep = requests.get(f'https://finance.sina.com.cn/realstock/company/sh{code}/nc.shtml')
    else:
        rep = requests.get(f'https://finance.sina.com.cn/realstock/company/sz{code}/nc.shtml')
    rep.encoding = 'utf-8'
    bs = bs4.BeautifulSoup(rep.content, 'lxml')
    body = bs.find('h1', {"id": 'stockName'})
    name = body.find_next('i').text
    return name


class StockInfo:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @lru_cache
    def __init__(self, headless=False, fine_update=False, simulate=True):

        self.area_classify_link = r'http://www.sse.com.cn/assortment/stock/areatrade/area/'
        self.industry_classify_link = r'http://www.sse.com.cn/assortment/stock/areatrade/trade/'
        self.specified_industry_base = r'http://www.sse.com.cn/assortment/stock/areatrade/trade/detail.shtml?csrcCode='
        self.prefix = r'http://www.sse.com.cn'
        self.historical_link_base = r'http://www.sse.com.cn/market/stockdata/overview/'
        if simulate:
            self.driver = args.Driver(headless=headless).blank_driver
            print('simulate mode')
        else:
            print('none mode')
        self.fine_update = fine_update
        if not os.path.exists('basic_html'):
            os.makedirs('basic_html')

    def hist_date_list(self, previous: int = 7):
        hist_data = stock_zh_a_hist(symbol='601318', start_date='2023-01-01', period='daily', adjust='').iloc[
                    -previous:, 0]
        return list(hist_data)

    @property
    def area_df(self):
        """
        This func aims to get the area data (for drawing the stocks nums of each province)
        :return: area df
        """

        area_df = pd.DataFrame(columns=['area', 'A', 'AB', 'B'])

        rep = requests.get(self.area_classify_link, headers=args.headers_area)
        rep.encoding = 'utf-8'
        text = rep.text
        text = repr(text).replace(r'\n', '').replace(r'\t', '').replace(' ', '').replace(r'\r', '').replace(r'\\', '')


        t = re.findall(r"\[\\'<atarget.*?]", text)
        for item in t:
            # print(item)
            area = re.findall('>(.*?)<', item)[0]
            digits = re.findall(r"'(\d*?)\\", item)
            digits = [int(i) for i in digits]
            # print(digits)
            a, ab, b = digits[:]
            # print(area, a, ab, b)
            # quit()
            area_df.loc[t.index(item)] = area, a, ab, b
        return area_df

    def draw_area_chart(self, render=True, df=pd.DataFrame()):
        df = df if not df.empty else self.area_df
        # print(df)
        province = list(df['area'])
        A_shares = list(df['A'])
        for i in range(len(province)):
            if province[i] in ['北京', '重庆', '天津', '上海']:
                province[i] = province[i] + '市'
            elif province[i] in ['内蒙古', '西藏']:
                province[i] = province[i] + '自治区'
            elif province[i] in ['新疆']:
                province[i] = province[i] + '维吾尔自治区'
            elif province[i] in ['宁夏']:
                province[i] = province[i] + '回族自治区'
            elif province[i] in ['广西']:
                province[i] = province[i] + '壮族自治区'
            else:
                province[i] = province[i] + '省'
        c = (
            Map()
                .add("A股发行数量", [list(z) for z in zip(province, A_shares)], "china",
                     is_map_symbol_show=False,
                     layout_center=['100%', '5%'])
                .set_series_opts(label_opts=opts.LabelOpts(is_show=False))
                .set_global_opts(
                title_opts=opts.TitleOpts(title="A SHARE DISTRIBUTION", is_show=True),
                visualmap_opts=opts.VisualMapOpts(max_=80, is_show=True, pos_left='200', pos_bottom='250', ),
                datazoom_opts=opts.DataZoomOpts(is_zoom_lock=True)

            )

        )  # render if not rendered, c is a Map, else a str of path
        if render:
            c.render("./basic_html/area_distribution.html")

        return c

    @property
    def rough_industry_df(self):
        rough_industry_df = pd.DataFrame(
            columns=['href', 'industry', 'industry_code', 'share_num', 'total_value', 'ave_pe', 'ave_price'])

        with open('trade.html', 'r+', encoding='utf-8') as f:
            bs = bs4.BeautifulSoup(f, 'lxml')
        t = bs.find("div", {"class": "sse_colContent js_tradeClassification"})
        t = t.find("script")
        text = repr(str(t)).replace(r'\n', '').replace(r'\t', '').replace(' ', '').replace(r'\r', '')
        l = re.findall(r"\[\\'<ahref.*?]", text)
        for item in l:
            href = self.prefix + re.findall(r'"(.*?)"', item)[0]
            rough_industry = re.findall(r'>(.*?)</a', item)[0]
            industry_code = href[-1]
            digits = re.findall(r"'([\d|\.|\-]*?)\\", item)
            digits = [float(i.replace('-', '0')) for i in digits]
            # print(item)
            share_num, total_value, ave_pe, ave_prive = digits[:]
            rough_industry_df.loc[
                l.index(item)] = href, rough_industry, industry_code, share_num, total_value, ave_pe, ave_prive

        return rough_industry_df

    @property
    def fine_industry_df(self):
        fine_industry_df = pd.DataFrame(
            columns=['href', 'industry', 'industry_code', 'share_num', 'total_value', 'ave_pe', 'ave_price'])
        if self.fine_update:
            self.driver.get(self.industry_classify_link)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located(
                (By.XPATH, r'/html/body/div[9]/div/div[2]/div/div[1]/div[1]/table/tbody[2]/tr[1]/td[2]')))
            page_source = self.driver.page_source
            with open('fine.html', 'w+', encoding='utf-8') as f:
                f.write(page_source)
        with open('fine.html', 'r+', encoding='utf-8') as f:
            h = f.read()

            bs = bs4.BeautifulSoup(h, 'lxml')
            main = bs.find_all('div', {"class": "table-responsive"})[0]

        l = main.find_all_next('tr')
        l = [str(i) for i in l]

        for field in l[1:]:
            field = str(field)
            href = self.prefix + re.findall(r'<a href="(.*?)"', field)[0]
            code = href[-3:]
            fine_industry = re.findall(r'blank">(.*?)</a', field)[0]
            digits = re.findall(r'>([\d|\.]+?)<', field)
            digits = [float(i) for i in digits]
            share_num, total_value, ave_pe, ave_prive = digits[:]
            fine_industry_df.loc[
                l.index(field)] = href, fine_industry, code, share_num, total_value, ave_pe, ave_prive
        return fine_industry_df

    def draw_classify_chart(self, df, render=True):
        rough_df = df
        c = (
            Bar()
                .add_xaxis(list(rough_df['industry']))
                .add_yaxis("总股数", list(rough_df['share_num']), is_selected=False)
                .add_yaxis("市盈率", list(rough_df['ave_pe']))
                .add_yaxis("平均股价", list(rough_df['ave_price']))
                .set_series_opts(label_opts=opts.LabelOpts(is_show=False))
                .set_global_opts(title_opts=opts.TitleOpts(title="分类"),
                                 xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-60)),
                                 datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=30),
                                                opts.DataZoomOpts(type_="inside")],
                                 tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),

                                 )

        )
        if len(df) == len(self.rough_industry_df):
            c.add_yaxis("总市值(千亿)", list(round(rough_df['total_value'] / 1e11, 2)))
            c.set_series_opts(label_opts=opts.LabelOpts(is_show=False))

            if render:
                c.render('./basic_html/rough_chart.html')

        elif len(df) == len(self.fine_industry_df):
            c.add_yaxis("总市值(百亿)", list(round(rough_df['total_value'] / 1e10, 2)))
            c.set_series_opts(label_opts=opts.LabelOpts(is_show=False))

            if render:
                c.render('./basic_html/fine_chart.html')
        else:
            raise ValueError
        return c

    def code_select(self):

        # selenium attempt
        industry_html_folder_path = r'fine_field_html_folder'
        industry_csv_folder_path = r'fine_field_csv_folder'

        if not os.path.exists(industry_html_folder_path):
            os.makedirs(industry_html_folder_path)
        if not os.path.exists(industry_csv_folder_path):
            os.makedirs(industry_csv_folder_path)
        hrefs = self.fine_industry_df['href']
        codes = self.fine_industry_df['industry_code']
        industries = self.fine_industry_df['industry']
        for href, industry_code, industry in tzip(hrefs, codes, industries):
            df = pd.DataFrame(columns=['name', 'share_code', 'industry', 'industry_code'])

            path = os.path.join(industry_html_folder_path, f'{industry_code}.html')
            self.driver.get(href)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, r'text-nowrap')))
            with open(path, 'w+', encoding='utf-8') as f:
                f.write(self.driver.page_source)

            with open(path, 'r+', encoding='utf-8') as f:
                h = f.read()
            bs = bs4.BeautifulSoup(h, 'lxml')
            l = bs.find_all('tr')
            l = [str(i) for i in l][1:]
            for comp in l:
                share_code = re.findall(r'blank">(\d*?)</a', comp)[0]
                name = re.findall(r'/a></td><td class.*?>(.*?)</td>', comp)[0]
                # print(l.index(comp))
                df.loc[l.index(comp)] = name, share_code, industry, industry_code
            df.to_csv(os.path.join(industry_csv_folder_path, f'{industry_code}.csv'))
            # quit()


    def macro_by_requests(self, previous=60):
        ua = UserAgent()
        headers = {
            'Referer': 'http://www.sse.com.cn/',

            'User-Agent': ua.random
        }
        session = requests.Session()
        session.get('http://www.sse.com.cn/', headers=headers)
        print(self.hist_date_list(previous=2)[:-1])

        h_data_dict_list = []
        dl = self.hist_date_list(previous=previous)
        for date in tqdm(dl):
            a = int(time.time() - 30) * 1000 - 100
            url = f'http://query.sse.com.cn/commonQuery.do?jsonCallBack=jsonpCallback32438768&sqlId=COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C&PRODUCT_CODE=01%2C02%2C03%2C11%2C17&type=inParams&SEARCH_DATE={date}&_={a}'
            resp2 = session.get(url, headers=headers)
            resp2.encoding = args.encoding
            content = resp2.text
            content = re.findall(pattern=f'.*?\((.*?)\)', string=content)[0]
            try:
                content = json.loads(content)['result'][0]
                h_data_dict_list.append(content)
            except Exception:
                continue

        df = pd.DataFrame(data=h_data_dict_list, index=dl)
        df = df[
            ['TOTAL_VALUE', 'NEGO_VALUE', 'TRADE_VOL', 'TRADE_AMT', 'AVG_PE_RATE', 'TOTAL_TO_RATE', 'NEGO_TO_RATE', ]]
        df.to_csv('macro_hist.csv')

    def draw_macro(self, render=True, previous=7):

        df = pd.read_csv('macro_hist.csv', index_col=0)[-previous:]

        # print(df)
        c = (
            Line()
                .add_xaxis(list(df.index))
                .add_yaxis("Vol(百亿)", list(round(df['TRADE_VOL'] / 1e2, 2)),
                           )
                .add_yaxis("Amount(千亿)", list(round(df['TRADE_AMT'] / 1e3, 2)),
                           )
                .add_yaxis("市盈率", df['AVG_PE_RATE'],
                           is_selected=False
                           )
                .add_yaxis(
                "换手率",
                df['TOTAL_TO_RATE'],
            )
                .add_yaxis(
                "流通换手率",
                df['NEGO_TO_RATE'], is_selected=False
            )
                .set_global_opts(title_opts=opts.TitleOpts(title="Overview"),
                                 datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100),
                                                opts.DataZoomOpts(type_="inside")],
                                 xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-60)),
                                 yaxis_opts=opts.AxisOpts(is_scale=True),
                                 tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),

                                 )
                .set_series_opts(label_opts=opts.LabelOpts(is_show=False),
                                 )
        )
        if render:
            c.render("./basic_html/macro_hist.html")
        else:
            return c

    def industry_df_list(self, industry: str = 'A01', previous=7):
        industry_df = pd.read_csv(f'fine_field_csv_folder/{industry}.csv', index_col=0)
        share_list = industry_df.loc[:, 'share_code'].tolist()
        name_list = industry_df.loc[:, 'name'].tolist()

        df_list = []
        for i in share_list:
            try:
                df_list.append(
                    stock_zh_a_hist(symbol=str(i), start_date='2022-01-01', period='daily', adjust='').iloc[-previous:,
                    :6])
            except Exception:
                pass


        rise_list = []
        for i in range(len(df_list)):
            df_list[i].columns = ['date', 'open', 'close', 'high', 'low', 'volume', ]
            # choose the close price, since it's more meaningful
            close_ = df_list[i].iloc[0, 2]
            df_list[i][['open', 'close', 'high', 'low']] = df_list[i][['open', 'close', 'high', 'low']].apply(
                lambda x: x / close_, axis=1)
            rise_list.append(df_list[i].iloc[-1, 2] - df_list[i].iloc[0, 2])
        index_list = list(map(rise_list.index, heapq.nlargest(5, rise_list))
                          )
        return df_list, index_list

    def draw_industry(self, industry='A01', previous=7, render=True):
        fine_df = self.fine_industry_df

        index = fine_df[fine_df.industry_code == industry].index.tolist()[0]
        industry_cn_name = fine_df.loc[index, 'industry']
        industry_df = pd.read_csv(f'fine_field_csv_folder/{industry}.csv', index_col=0)
        share_list = industry_df.loc[:, 'share_code'].tolist()
        name_list = industry_df.loc[:, 'name'].tolist()
        df_list, index_list = self.industry_df_list(industry, previous=previous)

        c = (
            Line(init_opts=opts.InitOpts(width='1000px', height='1500px'))
                .add_xaxis(list(df_list[0]['date']))
        )
        total_list = [i for i in range(len(df_list))]
        uns = list(set(total_list) - set(index_list))
        for idx in index_list:
            c.add_yaxis(f"{name_list[idx]}: {share_list[idx]}", round(df_list[idx]["close"], 4).tolist())
        if len(uns) >= 15:
            uns = random.sample(uns, 10)

        for idx in uns:
            c.add_yaxis(f"{name_list[idx]}: {share_list[idx]}", round(df_list[idx]["close"], 4).tolist(),
                        is_selected=False)


        c.set_global_opts(title_opts=opts.TitleOpts(title=industry_cn_name, subtitle=industry),
                          xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=-60)),
                          yaxis_opts=opts.AxisOpts(is_scale=True),
                          legend_opts=opts.LegendOpts(type_='scroll', orient='horizontal', pos_top='5%'),
                          datazoom_opts=[opts.DataZoomOpts(range_start=0),
                                         opts.DataZoomOpts(type_="inside", range_start=0, range_end=100)],
                          tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),

                          )
        c.set_series_opts(label_opts=opts.LabelOpts(is_show=False))

        if not os.path.exists("industry_draw"):
            os.makedirs('industry_draw')
        if render:
            c.render(f'./industry_draw/{industry}.html')
        else:
            return c

    def single_query(self, code='600017', previous=7):
        df = stock_zh_a_hist(symbol=str(code), start_date='2020-01-01', period='daily', adjust='').iloc[-previous:, :6]
        df.columns = ['date', 'open', 'close', 'high', 'low', 'volume', ]
        ohlc = df[['open', 'close', 'low', 'high']]  # oclh结构
        v = df['volume']
        date = df['date'].tolist()
        data = np.array(ohlc).tolist()  # convert to list through np.array, since cannot convert df to list directly
        volumn = np.array(v).tolist()

        return date, data, volumn

    def single_query_2(self, code, seg='day'):
        code = str(code).strip()
        if code[:2] == '60' or code[:2] == '68':
            code = 'SH' + code
        else:
            code = 'SZ' + code
        url = f'https://stock.xueqiu.com/v5/stock/chart/kline.json?symbol={code}&begin={int(time.time()) * 1000}&period={seg}&type=before&count=-284&indicator=kline,pe,pb,ps,pcf,market_capital,agt,ggt,balance'
        session = args.snowball_session()
        rep = session.get(url, headers=args.snowball_simple_headers)
        rep.encoding = 'utf-8'
        # print(rep.url)
        # print(rep.status_code)
        a = rep.text
        l_a = json.loads(a)['data']

        df = pd.DataFrame(columns=l_a['column'], data=l_a['item'])
        df['timestamp'] = df['timestamp'].apply(lambda x: datetime.fromtimestamp(x / 1000).strftime("%Y-%m-%d"))
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        ohlc = df[['open', 'close', 'low', 'high']]  # oclh结构
        v = df['volume']
        date = df['timestamp'].tolist()
        data = np.array(ohlc).tolist()  # 通过np转为list
        volumn = np.array(v).tolist()

        return date, data, volumn

    def draw_single(self, code='600013', symbol='SH000001', previous=7, render=True, index=False, seg='day'):
        if not index:
            # date, data, volumn = self.single_query(code, previous=previous)
            date, data, volumn = self.single_query_2(code, seg=seg)
        else:
            snowball_index_df = self.index_snowball_query(symbol=symbol, seg=seg)
            date, data, volumn = snowball_index_df['timestamp'].tolist(), np.array(
                snowball_index_df[['open', 'close', 'low', 'high']]).tolist(), snowball_index_df['volume'].tolist()

        kline = (
            Kline()
                .add_xaxis(date)
                .add_yaxis(
                series_name="",
                y_axis=data,
                itemstyle_opts=opts.ItemStyleOpts(
                    color0="#ef232a",
                    color="#14b143",
                    border_color0="#ef232a",
                    border_color="#14b143",
                ),
                markpoint_opts=opts.MarkPointOpts(
                    data=[
                        opts.MarkPointItem(type_="max", name="最大值"),
                        opts.MarkPointItem(type_="min", name="最小值"),
                    ]
                ),
            )
                .set_global_opts(
                xaxis_opts=opts.AxisOpts(
                    type_="category",
                    is_scale=True,
                    boundary_gap=False,
                    axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                    splitline_opts=opts.SplitLineOpts(is_show=False),
                    split_number=20,
                    min_="dataMin",
                    max_="dataMax",
                ),
                yaxis_opts=opts.AxisOpts(
                    is_scale=True,
                    splitarea_opts=opts.SplitAreaOpts(
                        is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                    ),
                ),
                tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
                datazoom_opts=[opts.DataZoomOpts(
                    is_show=False, type_="inside", xaxis_index=[0, 0], range_end=100, range_start=85,
                ),
                    opts.DataZoomOpts(is_show=True, xaxis_index=[0, 1], range_end=100)
                ],
            )
        )
        if not index:
            kline.title_opts = opts.TitleOpts(title=code2cn_name(code), subtitle=code, ),
        else:
            kline.title_opts = opts.TitleOpts(title='', subtitle=symbol),

        bar_vol = (
            Bar()
                .add_xaxis(xaxis_data=date)
                .add_yaxis(
                series_name="",
                y_axis=volumn,
                xaxis_index=1,
                yaxis_index=1,
                label_opts=opts.LabelOpts(is_show=False),
                itemstyle_opts=opts.ItemStyleOpts(
                    color=JsCode(
                        """
                    function(params) {
                        var colorList;
                        if (barData[params.dataIndex][1] > barData[params.dataIndex][0]) {
                            colorList = '#14b143';
                        } else {
                            colorList = '#ef232a';
                        }
                        return colorList;
                    }
                    """
                    )
                )
            )
        )
        grid_chart = Grid(init_opts=opts.InitOpts(width="500px" if index else '1000px', height="600px"))
        grid_chart.add_js_funcs("var barData = {}".format(data))
        grid_chart.add(
            kline,
            grid_opts=opts.GridOpts(
                pos_left="5%", pos_right="1%", pos_top="5%", height="60%"
            )
        )
        grid_chart.add(
            bar_vol,
            grid_opts=opts.GridOpts(
                pos_left="5%", pos_right="1%", pos_top="70%", height="20%"
            )
        )
        if render:
            grid_chart.render("sss.html")

        return grid_chart

    def index_query(self, code='sh000001', ):
        url = r'https://finance.sina.com.cn/realstock/company/{}/hisdata/klc_kl.js'
        params = {"d": "2020_2_4"}
        res = requests.get(url.format(code), params=params)
        js_code = py_mini_racer.MiniRacer()
        js_code.eval(hk_js_decode)
        dict_list = js_code.call(
            "d", res.text.split("=")[1].split(";")[0].replace('"', "")
        )  # execute js to decipher it
        temp_df = pd.DataFrame(dict_list)
        temp_df["date"] = pd.to_datetime(temp_df["date"]).dt.date
        temp_df["close"] = pd.to_numeric(temp_df["close"])
        return temp_df

    def index_snowball_query(self, symbol='SH000001', seg='day'):
        long_period = ['day', 'week', 'month', 'quarter', ]
        url = f'https://stock.xueqiu.com/v5/stock/chart/kline.json?symbol={symbol}&begin={int(time.time()) * 1000}&period={seg}&type=before&count=-284&indicator=kline,pe,pb,ps,pcf,market_capital,agt,ggt,balance'
        session = args.snowball_session()

        rep = session.get(url, headers=args.snowball_simple_headers)
        rep.encoding = 'utf-8'
        print(rep.url)
        print(rep.status_code)

        with open('2.txt', 'w+', encoding='utf-8') as f:
            f.write(rep.text)

        with open('2.txt', 'r', encoding=args.encoding) as f:
            a = f.read()
        l_a = json.loads(a)['data']

        df = pd.DataFrame(columns=l_a['column'], data=l_a['item'])
        df['timestamp'] = df['timestamp'].apply(lambda x: datetime.fromtimestamp(x / 1000).strftime("%Y-%m-%d"))
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']]
        return df

    def draw_index(self, code='sh000001', previous=800, render=True):

        df = self.index_query(code, ).iloc[-previous:]

        date_list = df['date'].tolist()
        index_list = df['close'].tolist()
        name_dict = {'sh000001': '上证指数', 'sh000016': '上证50', 'sh000017': '新综指'}
        c = (
            Line()
                .add_xaxis(date_list)
                .add_yaxis(name_dict.get(code, 'Unknown Index'), index_list, is_smooth=True)
                .set_series_opts(
                areastyle_opts=opts.AreaStyleOpts(opacity=0.5),
                label_opts=opts.LabelOpts(is_show=False),
            )
                .set_global_opts(
                title_opts=opts.TitleOpts(title=name_dict.get(code, 'Unknown Index')),
                xaxis_opts=opts.AxisOpts(
                    axistick_opts=opts.AxisTickOpts(is_align_with_label=True),
                    is_scale=True,
                    boundary_gap=True,
                ),
                yaxis_opts=opts.AxisOpts(is_scale=True),
                datazoom_opts=[opts.DataZoomOpts(range_start=60, range_end=100),
                               opts.DataZoomOpts(type_="inside", range_start=0)],
                tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),

            )
        )
        if render:
            c.render('index')
        return c


