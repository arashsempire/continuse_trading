from numba import jit_module, int16, int32, int64, float32, float64, cuda
import numpy as np
import logging

# logger = logging.getLogger(__name__)

# def main_calculations(L_entry, L_target, L_stop, S_entry, S_target, S_stop, date, minutes_data_np):
#     long_target = None
#     long_stop = None
#     short_target = None
#     short_stop = None
#     trade_active = False
#     long_trade_active = False
#     short_trade_active = False

#     first_open_price = minutes_data_np[0, 0]
#     long_entry = first_open_price * (1 + L_entry / 10000)
#     short_entry = first_open_price * (1 + S_entry / 10000)

#     o_id = []
#     o_price, d_trade, e_price = [], [], []

#     for index, row in enumerate(minutes_data_np):
#         open_, high_, low_, close_ = row
#         date_ = np.int64(date[index])

#         if not trade_active:
#             long_entry_condition  = (low_ <= long_entry  <= high_) or (low_ >= long_entry)
#             short_entry_condition = (low_ <= short_entry <= high_) or (high_ <= short_entry)
            
#             if  long_entry_condition and short_entry_condition:
#                 continue

#             elif long_entry_condition:
#                 long_target  = long_entry * (1 + L_target / 10000)
#                 long_stop    = long_entry * (1 + L_stop / 10000)
#                 trade_active = True
#                 long_trade_active = True
#                 o_price.append(close_)
#                 d_trade.append(1)
#                 o_id.append(date_)
                
#             elif short_entry_condition:
#                 short_target  = short_entry * (1 + S_target / 10000)
#                 short_stop    = short_entry * (1 + S_stop / 10000)
#                 trade_active = True
#                 short_trade_active = True
#                 o_price.append(close_)
#                 d_trade.append(-1)
#                 o_id.append(date_)

#             else:
#                 continue

#         elif long_trade_active:

#             target_condition = high_ >= long_target
#             stop_condition   = low_  <= long_stop

#             if target_condition and stop_condition:
#                 continue

#             elif target_condition:
#                 long_stop   = long_target   * (1 + L_stop / 10000)
#                 long_target = long_target * (1 + L_target / 10000)
    
#             elif stop_condition:
#                 trade_active = False
#                 long_trade_active = False
#                 short_trade_active = False
#                 long_entry  = long_stop * (1 + L_entry / 10000)
#                 short_entry = long_stop * (1 + S_entry / 10000)
#                 e_price.append(close_)

#             else:
#                 continue

#         elif short_trade_active:

#             target_condition = low_  <= short_target
#             stop_condition   = high_ >= short_stop

#             if target_condition and stop_condition:
#                 continue

#             elif target_condition:
#                 short_stop   = short_target   * (1 + S_stop / 10000)
#                 short_target = short_target * (1 + S_target / 10000)

#             elif stop_condition:
#                 trade_active = False
#                 long_trade_active = False
#                 short_trade_active = False
#                 long_entry  = short_stop * (1 + L_entry / 10000)
#                 short_entry = short_stop * (1 + S_entry / 10000)
#                 e_price.append(close_)
                
#             else:
#                 continue
#     else:
#         if trade_active:
#             trade_active = False
#             long_trade_active = False
#             short_trade_active = False
#             e_price.append(close_)

#     o_id = np.array(o_id)

#     o_price = np.array(o_price)#.astype(np.float32)
#     e_price = np.array(e_price)#.astype(np.float32)
#     d_trade = np.array(d_trade, dtype=np.int16)
#     pnl1 = (e_price / o_price) * 0.998001
#     pnl2 = (o_price / e_price) * 0.998001
#     pnl = np.where(d_trade ==  1, pnl1, pnl2)
    
#     trade_count = pnl.shape[0]
#     L_entry_np = np.full(trade_count, L_entry, dtype=np.float32) /100
#     L_target_np = np.full(trade_count, L_target, dtype=np.float32) /100
#     L_stop_np = np.full(trade_count, L_stop, dtype=np.float32) /100
#     S_entry_np = np.full(trade_count, S_entry, dtype=np.float32) /100
#     S_target_np = np.full(trade_count, S_target, dtype=np.float32) /100
#     S_stop_np = np.full(trade_count, S_stop, dtype=np.float32) /100

#     return L_entry_np, L_target_np, L_stop_np, S_entry_np, S_target_np, S_stop_np, pnl, d_trade, o_id




def main_calculations(L_entry, L_target, L_stop, S_entry, S_target, S_stop, date, minutes_data_np):
    long_target = None
    long_stop = None
    short_target = None
    short_stop = None
    trade_active = False
    long_trade_active = False
    short_trade_active = False

    first_open_price = minutes_data_np[0, 0]
    long_entry = first_open_price * (1 + L_entry / 10000)
    short_entry = first_open_price * (1 + S_entry / 10000)

    o_id = []
    o_price, d_trade, e_price = [], [], []

    for index, row in enumerate(minutes_data_np):
        open_, high_, low_, close_ = row
        date_ = np.int64(date[index])

        if not trade_active:
            long_entry_condition  = (low_ <= long_entry  <= high_) or (low_ >= long_entry)
            short_entry_condition = (low_ <= short_entry <= high_) or (high_ <= short_entry)
            
            if  long_entry_condition and short_entry_condition:
                continue

            elif long_entry_condition:
                long_target  = long_entry * (1 + L_target / 10000)
                long_stop    = long_entry * (1 + L_stop / 10000)
                trade_active = True
                long_trade_active = True
                o_price.append(close_)
                d_trade.append(1)
                o_id.append(date_)
                
            elif short_entry_condition:
                short_target  = short_entry * (1 + S_target / 10000)
                short_stop    = short_entry * (1 + S_stop / 10000)
                trade_active = True
                short_trade_active = True
                o_price.append(close_)
                d_trade.append(-1)
                o_id.append(date_)

            else:
                continue

        elif long_trade_active:

            target_condition = high_ >= long_target
            stop_condition   = low_  <= long_stop

            if target_condition and stop_condition:
                continue

            elif target_condition:
                long_stop   = long_target   * (1 + L_stop / 10000)
                long_target = long_target * (1 + L_target / 10000)
    
            elif stop_condition:
                trade_active = False
                long_trade_active = False
                short_trade_active = False
                long_entry  = long_stop * (1 + L_entry / 10000)
                short_entry = long_stop * (1 + S_entry / 10000)
                e_price.append(close_)

            else:
                continue

        elif short_trade_active:

            target_condition = low_  <= short_target
            stop_condition   = high_ >= short_stop

            if target_condition and stop_condition:
                continue

            elif target_condition:
                short_stop   = short_target   * (1 + S_stop / 10000)
                short_target = short_target * (1 + S_target / 10000)

            elif stop_condition:
                trade_active = False
                long_trade_active = False
                short_trade_active = False
                long_entry  = short_stop * (1 + L_entry / 10000)
                short_entry = short_stop * (1 + S_entry / 10000)
                e_price.append(close_)
                
            else:
                continue
    else:
        if trade_active:
            trade_active = False
            long_trade_active = False
            short_trade_active = False
            e_price.append(close_)

    o_id = np.array(o_id)

    o_price = np.array(o_price)
    e_price = np.array(e_price)
    d_trade = np.array(d_trade, dtype=np.int16)
    pnl1 = (e_price / o_price) * 0.998001
    pnl2 = (o_price / e_price) * 0.998001
    pnl = np.where(d_trade ==  1, pnl1, pnl2)
    pnlp = np.where(d_trade ==  1, pnl1, 1)
    pnln = np.where(d_trade ==  -1, pnl2, 1)
    long_trades = np.where(d_trade == 1, 1, 0)
    
    countp = long_trades.sum()
    countn = (1 - long_trades).sum()
    count = pnl.shape[0]
    pnl_comp = (pnl.prod() - 1) * 100
    pnl_simp = pnl.sum()
    pnlp_comp = (pnlp.prod() - 1) * 100
    pnln_comp = (pnln.prod() - 1) * 100

    return L_entry/100, L_target/100, L_stop/100, S_entry/100, S_target/100, S_stop/100, pnl_comp, pnl_simp, count, pnlp_comp, countp, pnln_comp, countn




# def main_calculations2(L_entry, L_target, L_stop, S_entry, S_target, S_stop, date, month, year, minutes_data_np):

#     long_target = float64(0.0)
#     long_stop = float64(0.0)
#     short_target = float64(0.0)
#     short_stop = float64(0.0)
#     trade_active = False
#     long_trade_active = False
#     short_trade_active = False

#     first_open_price = minutes_data_np[0, 0]
#     long_entry = first_open_price * (1 + L_entry / 10000)
#     short_entry = first_open_price * (1 + S_entry / 10000)

#     o_id = []
#     o_price, d_trade, e_price = [], [], []
#     m_trade, y_trade = [], []

#     for index in range(minutes_data_np.shape[0]):
#         row = minutes_data_np[index]
#         open_, high_, low_, close_ = row
#         date_ = int64(date[index])
#         month_ = int32(month[index])
#         year_ = int32(year[index])

#         if not trade_active:
#             long_entry_condition  = (low_ <= long_entry  <= high_) or (low_ >= long_entry)
#             short_entry_condition = (low_ <= short_entry <= high_) or (high_ <= short_entry)
            
#             if long_entry_condition and short_entry_condition:
#                 continue

#             elif long_entry_condition:
#                 long_target  = long_entry * (1 + L_target / 10000)
#                 long_stop    = long_entry * (1 + L_stop / 10000)
#                 trade_active = True
#                 long_trade_active = True
#                 o_price.append(close_)
#                 d_trade.append(1)
#                 m_trade.append(month_)
#                 y_trade.append(year_)
#                 o_id.append(date_)
                
#             elif short_entry_condition:
#                 short_target  = short_entry * (1 + S_target / 10000)
#                 short_stop    = short_entry * (1 + S_stop / 10000)
#                 trade_active = True
#                 short_trade_active = True
#                 o_price.append(close_)
#                 d_trade.append(-1)
#                 m_trade.append(month_)
#                 y_trade.append(year_)
#                 o_id.append(date_)

#             else:
#                 continue

#         elif long_trade_active:

#             target_condition = high_ >= long_target
#             stop_condition   = low_  <= long_stop

#             if target_condition and stop_condition:
#                 continue

#             elif target_condition:
#                 long_stop   = long_target   * (1 + L_stop / 10000)
#                 long_target = long_target * (1 + L_target / 10000)
    
#             elif stop_condition:
#                 trade_active = False
#                 long_trade_active = False
#                 short_trade_active = False
#                 long_entry  = long_stop * (1 + L_entry / 10000)
#                 short_entry = long_stop * (1 + S_entry / 10000)
#                 e_price.append(close_)

#             else:
#                 continue

#         elif short_trade_active:

#             target_condition = low_  <= short_target
#             stop_condition   = high_ >= short_stop

#             if target_condition and stop_condition:
#                 continue

#             elif target_condition:
#                 short_stop   = short_target   * (1 + S_stop / 10000)
#                 short_target = short_target * (1 + S_target / 10000)

#             elif stop_condition:
#                 trade_active = False
#                 long_trade_active = False
#                 short_trade_active = False
#                 long_entry  = short_stop * (1 + L_entry / 10000)
#                 short_entry = short_stop * (1 + S_entry / 10000)
#                 e_price.append(close_)
                
#             else:
#                 continue
#     else:
#         if trade_active:
#             trade_active = False
#             long_trade_active = False
#             short_trade_active = False
#             e_price.append(close_)

#     o_id = np.array(o_id, dtype=np.int32)
#     m_trade = np.array(m_trade, dtype=np.int32)
#     y_trade = np.array(y_trade, dtype=np.int32)
#     o_price = np.array(o_price, dtype=np.float64)
#     e_price = np.array(e_price, dtype=np.float64)
#     d_trade = np.array(d_trade, dtype=np.int16)

#     pnlu = (e_price / o_price) * 0.998001
#     pnld = (o_price / e_price) * 0.998001

#     pnl = np.where(d_trade == 1, pnlu, pnld)

#     trade_count = pnl.shape[0]
#     np_trades = np.vstack((
#         np.full(trade_count, np.round(L_entry   / 100, 2), dtype=np.float32),
#         np.full(trade_count, np.round(L_target  / 100, 2), dtype=np.float32),
#         np.full(trade_count, np.round(L_stop    / 100, 2), dtype=np.float32),
#         np.full(trade_count, np.round(S_entry   / 100, 2), dtype=np.float32),
#         np.full(trade_count, np.round(S_target  / 100, 2), dtype=np.float32),
#         np.full(trade_count, np.round(S_stop    / 100, 2), dtype=np.float32),
#         m_trade, y_trade, d_trade, pnl, o_id
#     )).T

#     # Manual aggregation
#     unique_keys = []
#     comp_pnl = []
#     simp_pnl = []
#     count_trades = []
#     if trade_count == 0:
#         return np.empty((0, 13))

#     for i in range(trade_count):
#         key = (np_trades[i, 0], np_trades[i, 1], np_trades[i, 2], np_trades[i, 3], np_trades[i, 4], np_trades[i, 5], np_trades[i, 6], np_trades[i, 7], np_trades[i, 8])
#         found = False

#         for j in range(len(unique_keys)):
#             if unique_keys[j] == key:
#                 found = True
#                 idx = j
#                 pnl_value = np_trades[i, 9]
#                 comp_pnl[idx] = comp_pnl[idx] * pnl_value if count_trades[idx] > 0 else pnl_value
#                 simp_pnl[idx] += (pnl_value - 1)
#                 count_trades[idx] += 1
#                 break
        
#         if not found:
#             unique_keys.append(key)
#             comp_pnl.append(np_trades[i, 9])
#             simp_pnl.append(np_trades[i, 9] - 1)
#             count_trades.append(1)

#     comp_pnl = np.array(comp_pnl, dtype=np.float64)
#     simp_pnl = np.array(simp_pnl, dtype=np.float64)
#     count_trades = np.array(count_trades, dtype=np.int32)

#     comp_pnl = (comp_pnl - 1) * 100
#     simp_pnl = simp_pnl * 100

#     unique_keys = np.array(unique_keys)
#     results = np.hstack((unique_keys, comp_pnl[:, np.newaxis], simp_pnl[:, np.newaxis], count_trades[:, np.newaxis]))
#     return results




def main_calculations2(L_entry, L_target, L_stop, S_entry, S_target, S_stop, date, month, year, minutes_data_np):

    long_target = float64(0.0)
    long_stop = float64(0.0)
    short_target = float64(0.0)
    short_stop = float64(0.0)
    trade_active = False
    long_trade_active = False
    short_trade_active = False

    first_open_price = minutes_data_np[0, 0]
    long_entry = first_open_price * (1 + L_entry / 10000)
    short_entry = first_open_price * (1 + S_entry / 10000)

    o_id = []
    o_price, d_trade, e_price = [], [], []
    m_trade, y_trade = [], []

    for index in range(minutes_data_np.shape[0]):
        row = minutes_data_np[index]
        open_, high_, low_, close_ = row
        date_ = int64(date[index])
        month_ = int32(month[index])
        year_ = int32(year[index])

        if not trade_active:
            long_entry_condition  = (low_ <= long_entry  <= high_) or (low_ >= long_entry)
            short_entry_condition = (low_ <= short_entry <= high_) or (high_ <= short_entry)
            
            if long_entry_condition and short_entry_condition:
                continue

            elif long_entry_condition:
                long_target  = long_entry * (1 + L_target / 10000)
                long_stop    = long_entry * (1 + L_stop / 10000)
                trade_active = True
                long_trade_active = True
                o_price.append(close_)
                d_trade.append(1)
                m_trade.append(month_)
                y_trade.append(year_)
                o_id.append(date_)
                
            elif short_entry_condition:
                short_target  = short_entry * (1 + S_target / 10000)
                short_stop    = short_entry * (1 + S_stop / 10000)
                trade_active = True
                short_trade_active = True
                o_price.append(close_)
                d_trade.append(-1)
                m_trade.append(month_)
                y_trade.append(year_)
                o_id.append(date_)

            else:
                continue

        elif long_trade_active:

            target_condition = high_ >= long_target
            stop_condition   = low_  <= long_stop

            if target_condition and stop_condition:
                continue

            elif target_condition:
                long_stop   = long_target   * (1 + L_stop / 10000)
                long_target = long_target * (1 + L_target / 10000)
    
            elif stop_condition:
                trade_active = False
                long_trade_active = False
                short_trade_active = False
                long_entry  = long_stop * (1 + L_entry / 10000)
                short_entry = long_stop * (1 + S_entry / 10000)
                e_price.append(close_)

            else:
                continue

        elif short_trade_active:

            target_condition = low_  <= short_target
            stop_condition   = high_ >= short_stop

            if target_condition and stop_condition:
                continue

            elif target_condition:
                short_stop   = short_target   * (1 + S_stop / 10000)
                short_target = short_target * (1 + S_target / 10000)

            elif stop_condition:
                trade_active = False
                long_trade_active = False
                short_trade_active = False
                long_entry  = short_stop * (1 + L_entry / 10000)
                short_entry = short_stop * (1 + S_entry / 10000)
                e_price.append(close_)
                
            else:
                continue
    else:
        if trade_active:
            trade_active = False
            long_trade_active = False
            short_trade_active = False
            e_price.append(close_)

    o_id = np.array(o_id, dtype=np.int32)
    m_trade = np.array(m_trade, dtype=np.int32)
    y_trade = np.array(y_trade, dtype=np.int32)
    o_price = np.array(o_price, dtype=np.float64)
    e_price = np.array(e_price, dtype=np.float64)
    d_trade = np.array(d_trade, dtype=np.int16)

    pnlu = (e_price / o_price) * 0.998001
    pnld = (o_price / e_price) * 0.998001

    pnl = np.where(d_trade == 1, pnlu, pnld)

    trade_count = pnl.shape[0]
    np_trades = np.vstack((
        np.full(trade_count, np.round(L_entry   / 100, 2), dtype=np.float32),
        np.full(trade_count, np.round(L_target  / 100, 2), dtype=np.float32),
        np.full(trade_count, np.round(L_stop    / 100, 2), dtype=np.float32),
        np.full(trade_count, np.round(S_entry   / 100, 2), dtype=np.float32),
        np.full(trade_count, np.round(S_target  / 100, 2), dtype=np.float32),
        np.full(trade_count, np.round(S_stop    / 100, 2), dtype=np.float32),
        m_trade, y_trade, pnl, o_id
    )).T

    # Manual aggregation
    unique_keys = []
    comp_pnl = []
    simp_pnl = []
    count_trades = []
    if trade_count == 0:
        return np.empty((0, 13))

    for i in range(trade_count):
        key = (np_trades[i, 0], np_trades[i, 1], np_trades[i, 2], np_trades[i, 3], np_trades[i, 4], np_trades[i, 5], np_trades[i, 6], np_trades[i, 7])
        found = False

        for j in range(len(unique_keys)):
            if unique_keys[j] == key:
                found = True
                idx = j
                pnl_value = np_trades[i, 8]
                comp_pnl[idx] = comp_pnl[idx] * pnl_value if count_trades[idx] > 0 else pnl_value
                simp_pnl[idx] += (pnl_value - 1)
                count_trades[idx] += 1
                break
        
        if not found:
            unique_keys.append(key)
            comp_pnl.append(np_trades[i, 8])
            simp_pnl.append(np_trades[i, 8] - 1)
            count_trades.append(1)

    comp_pnl = np.array(comp_pnl, dtype=np.float64)
    simp_pnl = np.array(simp_pnl, dtype=np.float64)
    count_trades = np.array(count_trades, dtype=np.int32)

    comp_pnl = (comp_pnl - 1) * 100
    simp_pnl = simp_pnl * 100

    unique_keys = np.array(unique_keys)
    results = np.hstack((unique_keys, comp_pnl[:, np.newaxis], count_trades[:, np.newaxis]))
    return results


jit_module(parallel=True, nopython=True)
