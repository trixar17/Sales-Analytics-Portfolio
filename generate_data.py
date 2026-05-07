"""
============================================================================
 Synthetic Data Generator (CSV-only version)
============================================================================
 Purpose
   - Create a synthetic dataset that simulates sales/distribution/CRM data.
   - Designed for a Tableau dashboard portfolio (star-schema based).

 Reference Date
   - 2026-05-01 (assumed "today")
   - Data range: 2024-05-01 ~ 2026-04-30 (trailing 24 months)

 Output
   - 7 CSV files in ./data/
   - Encoded as UTF-8 with BOM (prevents Korean character corruption
     when imported into Tableau)
   - Star Schema layout:
        Dimensions: dim_partner, dim_product, dim_date
        Facts     : fact_sales, fact_traffic, fact_promotion, fact_crm

 Author : Sunghoon Jun
 Updated: 2026-05-06
============================================================================
"""
import os
import random
import numpy as np
import pandas as pd
from datetime import date, timedelta
from faker import Faker

# ============================================================================
# Configuration
# ============================================================================
# Fix all random seeds to guarantee reproducibility.
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker('ko_KR')      # Korean locale (names, addresses, company names)
Faker.seed(SEED)

# Two years of daily data
START_DATE = date(2024, 5, 1)          # fixed start date
END_DATE   = date(2026, 4, 30)         # fixed end date
OUTPUT_DIR = './data'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Entity sizes — scaled-down approximation of real footprint
N_PARTNERS  = 80          # distribution partners (Premium Reseller, Carrier, etc.)
N_PRODUCTS  = 200         # Products
N_CUSTOMERS = 100_000     # customer master (CRM)
N_PROMOS    = 36          # promotional campaigns

# ----------------------------------------------------------------------------
# 17 Korean administrative regions weighted by population.
# Reflects the real distribution where Seoul + Gyeonggi account for ~50%.
# ----------------------------------------------------------------------------
KOREA_REGIONS = [
    ('서울', 0.28), ('경기', 0.22), ('부산', 0.08), ('인천', 0.06),
    ('대구', 0.05), ('대전', 0.04), ('광주', 0.04), ('울산', 0.03),
    ('세종', 0.01), ('강원', 0.03), ('충북', 0.03), ('충남', 0.03),
    ('전북', 0.03), ('전남', 0.03), ('경북', 0.03), ('경남', 0.03),
    ('제주', 0.01),
]

# ----------------------------------------------------------------------------
# Partner tiers
#   Premium Reseller : flagship-tier stores
#   Authorized       : official authorized resellers
#   Carrier          : mobile carrier channels (SKT/KT/LGU+)
#   Online           : online store + e-commerce partners
# ----------------------------------------------------------------------------
TIERS = [('Premium Reseller', 0.20), ('Authorized', 0.40),
         ('Carrier',          0.25), ('Online',     0.15)]

# ----------------------------------------------------------------------------
# Product lines — (line name, revenue weight, price range in KRW)
# iPhone drives ~55% of revenue, mirroring Apple's product mix.
# ----------------------------------------------------------------------------
PRODUCT_LINES = [
    ('iPhone',      0.55, (1_200_000, 2_400_000)),
    ('iPad',        0.15, (  600_000, 1_800_000)),
    ('Mac',         0.15, (1_800_000, 4_500_000)),
    ('Watch',       0.08, (  400_000, 1_200_000)),
    ('Accessories', 0.07, (   30_000,   400_000)),
]

# Promotional offer types / customer segments / payment methods
OFFER_TYPES = ['Trade-in', 'Bundle', 'Cashback', 'Direct Discount']
SEGMENTS    = [('Premium', 0.20), ('Mid', 0.50), ('Entry', 0.30)]
PAY_METHODS = [('Card', 0.55), ('Installment', 0.30), ('Carrier Subscription', 0.15)]


def weighted_choice(pairs):
    """
    Helper: weighted random selection.

    Args:
        pairs: list of (item, weight) tuples
    Returns:
        a single item chosen according to the weights
    """
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]


# ============================================================================
# 1. dim_partner — Partner dimension table
# ============================================================================
def gen_partners():
    rows = []
    for i in range(1, N_PARTNERS + 1):
        tier   = weighted_choice(TIERS)            # weighted tier assignment
        region = weighted_choice(KOREA_REGIONS)    # population-weighted region
        # Store opening date — random between 2018 and 2024 to create
        opened = fake.date_between(start_date=date(2018, 1, 1),
                                   end_date=date(2024, 12, 31))
        rows.append({
            'partner_id':        f'PT{i:05d}',                       # zero-padded 5-digit ID
            'partner_name':      f'{fake.company()} {tier.split()[0]}',
            'partner_tier':      tier,
            'region':            region,
            'city':              fake.city(),
            'opened_date':       opened,
            'parent_partner_id': '',                            # default: standalone
            'is_active': 1,                                     # all currently active
        })
    df = pd.DataFrame(rows)

    # ------------------------------------------------------------------------
    # 20 random child stores under Premium Reseller parents.
    # ------------------------------------------------------------------------
    premium_ids = df[df['partner_tier'] == 'Premium Reseller']['partner_id'].tolist()
    for pid in df.sample(20, random_state=SEED)['partner_id']:
        if pid in premium_ids:
            continue   # Premium parents shouldn't become children themselves
        df.loc[df['partner_id'] == pid, 'parent_partner_id'] = random.choice(premium_ids)
    return df


# ============================================================================
# 2. dim_product — Product dimension table
#    Holds line-level price ranges and an `is_current` flag for
#    "new vs. legacy" comparisons.
# ============================================================================
def gen_products():
    rows = []
    for i in range(1, N_PRODUCTS + 1):
        # Pick a product line by weight (iPhone is most likely)
        line = weighted_choice([(l, w) for l, w, _ in PRODUCT_LINES])
        # Look up the line's price range
        price_range = next(r for l, _, r in PRODUCT_LINES if l == line)
        # Round MSRP to the nearest 10,000 KRW to mimic real retail pricing
        msrp = int(np.random.uniform(*price_range) // 10_000 * 10_000)
        # Launch dates limited to 2022 onward
        launch = fake.date_between(start_date=date(2022, 1, 1),
                                   end_date=date(2026, 3, 1))
        rows.append({
            'sku': f'{line[:3].upper()}-{i:04d}',           # e.g., IPH-0001
            'product_line': line,
            'product_name': f'{line} Model {i}',
            'launch_date':  launch,
            'msrp_krw':     msrp,
            # Models launched on/after 2024-01-01 are flagged "current"
            'is_current':   1 if launch >= date(2024, 1, 1) else 0,
        })
    return pd.DataFrame(rows)


# ============================================================================
# 3. dim_date — Date dimension (calendar table)
#    Supports time-based analysis
#    Fiscal Year starts in October (FY2025 = Oct 2024 ~ Sep 2025).
# ============================================================================
def gen_dates():
    rows = []
    d = START_DATE
    while d <= END_DATE:
        m = d.month
        # fiscal-quarter mapping
        if   m in (10, 11, 12): fq = f'FY{d.year+1}-Q1'   # Q1: Oct~Dec
        elif m in (1, 2, 3):    fq = f'FY{d.year}-Q2'     # Q2: Jan~Mar
        elif m in (4, 5, 6):    fq = f'FY{d.year}-Q3'     # Q3: Apr~Jun
        else:                   fq = f'FY{d.year}-Q4'     # Q4: Jul~Sep
        rows.append({
            'date_key':       d,
            'year':           d.year,
            'quarter':        (m - 1)//3 + 1,                   # standard calendar quarter
            'month':          m,
            'week':           int(d.strftime('%V')),            # ISO week number
            'day_of_week':    d.weekday(),                   # 0=Mon, 6=Sun
            'is_weekend':     1 if d.weekday() >= 5 else 0,
            'fiscal_quarter': fq,                         # fiscal quarter
        })
        d += timedelta(days=1)
    return pd.DataFrame(rows)


# ============================================================================
# 4. fact_promotion — Promotion fact table
#    join to fact_sales.
# ============================================================================
def gen_promotions():
    rows = []
    for i in range(1, N_PROMOS + 1):
        # Cap start dates 30 days before END_DATE so campaigns stay in range
        start = fake.date_between(start_date=START_DATE,
                                  end_date=END_DATE - timedelta(days=30))
        duration = random.choice([7, 14, 21, 30])         # 1/2/3-week or monthly
        end = min(start + timedelta(days=duration), END_DATE)
        rows.append({
            # Promo ID encodes the starting fiscal quarter (e.g., PR2025Q3-007)
            'promo_id':  f'PR{start.year}{(start.month-1)//3+1}-{i:03d}',
            'promo_name': random.choice([
                'iPhone Launch Special', 'Back to School', 'Trade-in Boost',
                'Carrier Bundle Deal', 'Holiday Cashback', 'Education Discount',
                'Lunar New Year Promo', 'Spring Festival', 'Black Friday KR',
            ]) + f' #{i}',
            'offer_type':          random.choice(OFFER_TYPES),
            'start_date':          start,
            'end_date':            end,
            'discount_pct':        round(np.random.uniform(0.05, 0.30), 2),   # 5%~30% off
            # Empty string means "applies to all lines / all tiers"
            'target_product_line': random.choice([''] + [l for l,_,_ in PRODUCT_LINES]),
            'target_tier':         random.choice([''] + [t for t,_ in TIERS]),
        })
    return pd.DataFrame(rows)


# ============================================================================
# 5. fact_sales — Sales fact table (largest, ~500K rows)
#    The central transactional table for daily/partner/product analysis.
#    Design highlights:
#      - Seasonality (Sep iPhone launch, Nov BFCM, Dec holidays)
#      - Year-over-year growth multipliers
#      - Weekend boost
# ============================================================================
def gen_sales(partners, products, promos):
    sales = []
    sale_id = 0
    # Dirichlet distribution → similar to 80/20
    partner_weights = np.random.dirichlet(np.ones(len(partners)) * 1.5)

    for d_offset in range((END_DATE - START_DATE).days + 1):
        cur_date = START_DATE + timedelta(days=d_offset)

        # --------------------------------------------------------------------
        # Seasonality multiplier — mirrors Apple's real revenue cadence
        #   Sep: iPhone launch        → ×1.6
        #   Nov: Black Friday/BFCM    → ×1.4
        #   Dec: holiday gifting      → ×1.5
        #   Weekends: foot traffic    → ×1.15 additional
        # --------------------------------------------------------------------
        seasonality = 1.0
        if cur_date.month == 9:     seasonality = 1.6
        if cur_date.month == 11:    seasonality = 1.4
        if cur_date.month == 12:    seasonality = 1.5
        if cur_date.weekday() >= 5: seasonality *= 1.15

        # YoY growth — +5% in 2025, +12% in 2026 (inflation + market expansion)
        if cur_date.year == 2025: seasonality *= 1.05
        if cur_date.year == 2026: seasonality *= 1.12

        # Daily transaction count — N(700, 120) scaled by seasonality, at least 200
        n_sales_today = int(np.random.normal(700, 120) * seasonality)
        n_sales_today = max(n_sales_today, 200)

        # Filter promotions active on this day
        active_promos = promos[(promos['start_date'] <= cur_date) &
                               (promos['end_date']   >= cur_date)]

        # Sample partners by weight, sample products uniformly with replacement
        chosen_partners = np.random.choice(partners['partner_id'].values,
                                           size=n_sales_today,
                                           p=partner_weights)
        chosen_products = products.sample(n_sales_today, replace=True)

        for pid, (_, prod) in zip(chosen_partners, chosen_products.iterrows()):
            # Quantity distribution — 90% single-item, occasional bundles
            units = np.random.choice([1, 1, 1, 2, 3], p=[0.7, 0.1, 0.1, 0.07, 0.03])
            gross = int(prod['msrp_krw'] * units)          # gross at MSRP

            # ----------------------------------------------------------------
            # Promotion logic
            #   - 25% chance to apply if any campaign is active
            #   - Applies only if the targeted line matches (or targets all)
            # ----------------------------------------------------------------
            promo_id = ''
            discount = 0
            if len(active_promos) > 0 and random.random() < 0.25:
                promo = active_promos.sample(1).iloc[0]
                if (promo['target_product_line'] == '' or
                    promo['target_product_line'] == prod['product_line']):
                    promo_id = promo['promo_id']
                    discount = int(gross * promo['discount_pct'])

            net = gross - discount                          # net = gross − discount
            sale_id += 1
            sales.append((sale_id, cur_date, pid, prod['sku'],
                          int(units), gross, discount, net, promo_id))

    df = pd.DataFrame(sales, columns=[
        'sale_id', 'sale_date', 'partner_id', 'sku', 'units',
        'gross_revenue_krw', 'discount_amount_krw', 'net_revenue_krw', 'promo_id'])

    return df


# ============================================================================
# 6. fact_traffic — Store/online traffic fact
# ============================================================================
def gen_traffic(partners):
    rows = []
    n_days = (END_DATE - START_DATE).days + 1
    for _, p in partners.iterrows():
        # Average sessions per channel — Online > Premium > Carrier > Authorized
        base = {'Premium Reseller': 4500, 'Authorized': 2200,
                'Carrier': 3000, 'Online': 8000}[p['partner_tier']]
        # Add-to-cart rate — Premium > Authorized > Carrier > Online
        atc_rate    = {'Premium Reseller': 0.65, 'Authorized': 0.55,
                       'Carrier': 0.45, 'Online': 0.50}[p['partner_tier']]
        # Final purchase rate — Premium > Authorized > Carrier > Online
        purch_rate  = {'Premium Reseller': 0.38, 'Authorized': 0.28,
                       'Carrier': 0.22, 'Online': 0.30}[p['partner_tier']]

        for d_offset in range(n_days):
            cur_date = START_DATE + timedelta(days=d_offset)
            # Daily sessions — normal distribution with ±20% volatility, at least 50
            sessions = max(int(np.random.normal(base, base*0.2)), 50)
            atc      = int(sessions * np.random.normal(atc_rate, 0.05))
            checkout = int(atc * np.random.uniform(0.55, 0.75))
            conv     = int(checkout * np.random.normal(purch_rate, 0.05))
            rows.append((cur_date, p['partner_id'],
                         sessions, atc, checkout, conv))
    df = pd.DataFrame(rows, columns=[
        'traffic_date', 'partner_id', 'sessions',
        'add_to_cart', 'checkout_started', 'conversions'])
    df.insert(0, 'traffic_id', range(1, len(df) + 1))     # surrogate key

    # ------------------------------------------------------------------------
    # Injected outlier — a partner with high traffic but abnormally low
    # conversion. Surfaces as a clear visual outlier in Dashboard 2's
    # scatter plot (traffic vs. conversion).
    # ------------------------------------------------------------------------
    anomaly_pid = partners.iloc[0]['partner_id']
    mask = df['partner_id'] == anomaly_pid
    df.loc[mask, 'sessions']    = (df.loc[mask, 'sessions']    * 3).astype(int)
    df.loc[mask, 'conversions'] = (df.loc[mask, 'conversions'] * 0.3).astype(int)
    return df


# ============================================================================
# 7. fact_crm — Customer master (CRM) fact
# ============================================================================
def gen_crm(partners):
    rows = []
    for i in range(1, N_CUSTOMERS + 1):
        # Random first-purchase date
        first = fake.date_between(start_date=START_DATE, end_date=END_DATE)
        # Order frequency — 55% one-timers, a small share of loyal repeat buyers
        total_orders = int(np.random.choice([1, 2, 3, 5, 10],
                                            p=[0.55, 0.25, 0.12, 0.06, 0.02]))
        # Last purchase — equals first for one-timers; later for repeaters
        last = first if total_orders == 1 else fake.date_between(
            start_date=first, end_date=END_DATE)
        seg = weighted_choice(SEGMENTS)
        # Base LTV by segment, with diminishing returns on order count (^0.4)
        ltv_base = {'Premium': 2_800_000, 'Mid': 1_500_000, 'Entry': 700_000}[seg]
        ltv = int(ltv_base * np.random.uniform(0.7, 1.3) * total_orders ** 0.4)
        rows.append({
            'customer_id':         f'CU{i:07d}',
            'partner_id':          random.choice(partners['partner_id'].tolist()),
            'first_purchase_date': first,
            'last_purchase_date':  last,
            'total_orders':        total_orders,
            'ltv_krw':             ltv,
            'segment':             seg,
            'payment_method':      weighted_choice(PAY_METHODS),
        })
    return pd.DataFrame(rows)


# ============================================================================
# Main — UTF-8 with BOM encoding (Tableau-friendly Korean support)
# ============================================================================
if __name__ == '__main__':
    enc = 'utf-8-sig'   # ★ BOM header prevents Korean garbling in Tableau

    # Dim tables first — facts reference these keys.
    print('▶ Generating dim_partner ...')
    partners = gen_partners()
    partners.to_csv(f'{OUTPUT_DIR}/dim_partner.csv', index=False, encoding=enc)

    print('▶ Generating dim_product ...')
    products = gen_products()
    products.to_csv(f'{OUTPUT_DIR}/dim_product.csv', index=False, encoding=enc)

    print('▶ Generating dim_date ...')
    dates = gen_dates()
    dates.to_csv(f'{OUTPUT_DIR}/dim_date.csv', index=False, encoding=enc)

    # Build fact tables that reference the dimensions above.
    print('▶ Generating fact_promotion ...')
    promos = gen_promotions()
    promos.to_csv(f'{OUTPUT_DIR}/fact_promotion.csv', index=False, encoding=enc)

    print('▶ Generating fact_sales ...')
    sales = gen_sales(partners, products, promos)
    sales.to_csv(f'{OUTPUT_DIR}/fact_sales.csv', index=False, encoding=enc)

    print('▶ Generating fact_traffic ...')
    traffic = gen_traffic(partners)
    traffic.to_csv(f'{OUTPUT_DIR}/fact_traffic.csv', index=False, encoding=enc)

    print('▶ Generating fact_crm ...')
    crm = gen_crm(partners)
    crm.to_csv(f'{OUTPUT_DIR}/fact_crm.csv', index=False, encoding=enc)

    # Final summary
    print('\n✅ Done. Summary:')
    print(f'  1. dim_partner   : {len(partners):>7,} rows')
    print(f'  2. dim_product   : {len(products):>7,} rows')
    print(f'  3. dim_date      : {len(dates):>7,} rows')
    print(f'  4. fact_promotion: {len(promos):>7,} rows')
    print(f'  5. fact_sales    : {len(sales):>7,} rows')
    print(f'  6. fact_traffic  : {len(traffic):>7,} rows')
    print(f'  7. fact_crm      : {len(crm):>7,} rows')
    
