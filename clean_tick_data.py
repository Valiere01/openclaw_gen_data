#!/usr/bin/env python3
"""Clean tick data for algo strategy validation."""
import csv
import re

INPUT_FILE = 'tick_data_raw.csv'
OUTPUT_FILE = 'tick_data_cleaned.csv'

def normalize_symbol(symbol_variant, ticker):
    """Normalize symbol_variant to match ticker casing."""
    if not symbol_variant:
        return ticker.upper() if ticker else ''
    # Remove suffixes like _US, extract base symbol
    base = re.sub(r'[_\-].*$', '', symbol_variant)
    # If ticker exists, use ticker; otherwise use normalized base
    if ticker:
        return ticker.upper()
    return base.upper()

def clean_data():
    stats = {
        'total_rows': 0,
        'null_timestamp': 0,
        'null_ticker': 0,
        'duplicates': 0,
        'zero_price': 0,
        'invalid_volume': 0,
        'symbol_normalized': 0,
        'final_rows': 0
    }
    
    cleaned_rows = []
    seen_keys = set()
    
    with open(INPUT_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats['total_rows'] += 1
            
            # Check null timestamp
            if not row['timestamp'] or row['timestamp'].strip() == '':
                stats['null_timestamp'] += 1
                continue
            
            # Check null ticker
            if not row['ticker'] or row['ticker'].strip() == '':
                stats['null_ticker'] += 1
                continue
            
            # Validate price (filter zero-price)
            try:
                price = float(row['price'])
                if price == 0:
                    stats['zero_price'] += 1
                    continue
            except (ValueError, TypeError):
                stats['zero_price'] += 1
                continue
            
            # Validate volume as integer
            try:
                volume = int(row['volume'])
            except (ValueError, TypeError):
                stats['invalid_volume'] += 1
                continue
            
            # Deduplicate on timestamp+price
            dedup_key = (row['timestamp'], str(price))
            if dedup_key in seen_keys:
                stats['duplicates'] += 1
                continue
            seen_keys.add(dedup_key)
            
            # Normalize symbol_variant
            original_symbol = row['symbol_variant']
            normalized_symbol = normalize_symbol(row['symbol_variant'], row['ticker'])
            if original_symbol != normalized_symbol:
                stats['symbol_normalized'] += 1
            
            cleaned_rows.append({
                'timestamp': row['timestamp'],
                'ticker': row['ticker'].upper(),
                'symbol_variant': normalized_symbol,
                'price': price,
                'volume': volume
            })
    
    stats['final_rows'] = len(cleaned_rows)
    
    # Write cleaned data
    with open(OUTPUT_FILE, 'w', newline='') as f:
        fieldnames = ['timestamp', 'ticker', 'symbol_variant', 'price', 'volume']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned_rows)
    
    return stats

if __name__ == '__main__':
    stats = clean_data()
    print("=== DATA CLEANING COMPLETE ===")
    print(f"Total input rows: {stats['total_rows']}")
    print(f"Null timestamps removed: {stats['null_timestamp']}")
    print(f"Null tickers removed: {stats['null_ticker']}")
    print(f"Duplicates removed: {stats['duplicates']}")
    print(f"Zero-price rows filtered: {stats['zero_price']}")
    print(f"Invalid volume rows: {stats['invalid_volume']}")
    print(f"Symbols normalized: {stats['symbol_normalized']}")
    print(f"Final clean records: {stats['final_rows']}")
    
    # Save stats for summary
    import json
    with open('cleaning_stats.json', 'w') as f:
        json.dump(stats, f, indent=2)
