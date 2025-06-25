import boto3
import pandas as pd
import numpy as np
from io import StringIO

s3 = boto3.client('s3')

def lambda_handler(event, context):
    try:
        bucket = event['Records'][0]['s3']['bucket']['name']
        raw_key = event['Records'][0]['s3']['object']['key']

        obj = s3.get_object(Bucket=bucket, Key=raw_key)
        raw_data = obj['Body'].read().decode('latin1')
        df = pd.read_csv(StringIO(raw_data))

        # Validar columnas mínimas
        for col in ['DEALSIZE', 'CONTACTFIRSTNAME', 'CITY', 'COUNTRY']:
            if col not in df.columns:
                df[col] = pd.NA

        # Limpieza de datos
        df.drop_duplicates(inplace=True)
        int_cols = ['ORDERNUMBER', 'QUANTITYORDERED', 'ORDERLINENUMBER', 'MONTH_ID', 'YEAR_ID', 'QTR_ID']
        for col in int_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

        df['PRICEEACH'] = pd.to_numeric(df['PRICEEACH'], errors='coerce').fillna(0).abs()
        df = df[df['PRICEEACH'] > 0]
        df['QUANTITYORDERED'] = pd.to_numeric(df['QUANTITYORDERED'], errors='coerce').fillna(0).astype(int)
        df = df[df['QUANTITYORDERED'] > 0]

        df['SALES'] = pd.to_numeric(df['SALES'], errors='coerce').fillna(0)
        expected = df['QUANTITYORDERED'] * df['PRICEEACH']
        df = df[np.isclose(df['SALES'], expected, rtol=0.05)]
        df['ORDERDATE'] = pd.to_datetime(df['ORDERDATE'], errors='coerce')
        df = df[(df['ORDERDATE'].dt.year >= 2000) & (df['ORDERDATE'].dt.year <= 2025)]
        df['ORDERDATE'] = df['ORDERDATE'].dt.date

        for col in ['POSTALCODE', 'TERRITORY', 'STATE']:
            df[col] = df[col].fillna('Unknown')

        df.dropna(subset=['CITY', 'COUNTRY'], inplace=True)
        df['NUMERICCODE'] = pd.to_numeric(df['NUMERICCODE'], errors='coerce')
        df['CONTACTLASTNAME'] = df['CONTACTLASTNAME'].str.title()
        df['CONTACTFIRSTNAME'] = df['CONTACTFIRSTNAME'].str.title()

        allowed = ['Small', 'Medium', 'Large']
        df = df[df['DEALSIZE'].isin(allowed)]

        if 'ADDRESSLINE2' in df.columns and df['ADDRESSLINE2'].isnull().all():
            df.drop(columns=['ADDRESSLINE2'], inplace=True)

        df = df.sort_values(by='ORDERDATE').drop_duplicates(subset='ORDERNUMBER', keep='last')

        json_data = df.to_json(orient='records', lines=True)
        process_key = raw_key.replace("raw/", "process/").replace(".csv", ".json")

        s3.put_object(Bucket=bucket, Key=process_key, Body=json_data.encode('utf-8'))

        return {
            'statusCode': 200,
            'body': f'Archivo limpio guardado en s3://{bucket}/{process_key}'
        }

    except Exception as e:
        print("❌ Error procesando el archivo:", str(e), flush=True)
        raise e
#a