import boto3
import pandas as pd
import numpy as np
from io import StringIO

s3 = boto3.client('s3')

def lambda_handler(event, context):
    # Extraer información del evento de S3
    bucket = event['Records'][0]['s3']['bucket']['name']
    raw_key = event['Records'][0]['s3']['object']['key']

    # Descargar archivo desde raw/
    raw_obj = s3.get_object(Bucket=bucket, Key=raw_key)
    raw_data = raw_obj['Body'].read().decode('latin1')
    df = pd.read_csv(StringIO(raw_data))

    # LIMPIEZA DE DATOS
    df.drop_duplicates(inplace=True)

    # Corregir tipos
    int_cols = ['ORDERNUMBER', 'QUANTITYORDERED', 'ORDERLINENUMBER', 'MONTH_ID', 'YEAR_ID', 'QTR_ID']
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    # Limpiar y validar precios
    df['PRICEEACH'] = pd.to_numeric(df['PRICEEACH'], errors='coerce').fillna(0).abs()
    df = df[df['PRICEEACH'] > 0]

    # Limpiar y validar cantidades
    df['QUANTITYORDERED'] = pd.to_numeric(df['QUANTITYORDERED'], errors='coerce').fillna(0).astype(int)
    df = df[df['QUANTITYORDERED'] > 0]

    # Validar consistencia de SALES
    df['SALES'] = pd.to_numeric(df['SALES'], errors='coerce').fillna(0)
    df['EXPECTED_SALES'] = df['QUANTITYORDERED'] * df['PRICEEACH']
    df = df[np.isclose(df['SALES'], df['EXPECTED_SALES'], rtol=0.05)]
    df.drop(columns=['EXPECTED_SALES'], inplace=True)

    # Validar fechas
    df['ORDERDATE'] = pd.to_datetime(df['ORDERDATE'], errors='coerce')
    df = df[(df['ORDERDATE'].dt.year >= 2000) & (df['ORDERDATE'].dt.year <= 2025)]
    df['ORDERDATE'] = df['ORDERDATE'].dt.date

    # Imputar valores nulos simples
    for col in ['POSTALCODE', 'TERRITORY', 'STATE']:
        df[col] = df[col].fillna('Unknown')

    # Validar columnas esenciales
    df.dropna(subset=['CITY', 'COUNTRY'], inplace=True)

    # Validar y limpiar NUMERICCODE
    df['NUMERICCODE'] = pd.to_numeric(df['NUMERICCODE'], errors='coerce')

    # Formatear nombres
    df['CONTACTLASTNAME'] = df['CONTACTLASTNAME'].str.title()
    df['CONTACTFIRSTNAME'] = df['CONTACTFIRSTNAME'].str.title()

    # Validar DEALSIZE
    allowed_deals = ['Small', 'Medium', 'Large']
    df = df[df['DEALSIZE'].isin(allowed_deals)]

    # Eliminar columnas completamente vacías
    if 'ADDRESSLINE2' in df.columns and df['ADDRESSLINE2'].isnull().all():
        df.drop(columns=['ADDRESSLINE2'], inplace=True)

    # Eliminar duplicados por ORDERNUMBER con diferencias
    df = df.sort_values(by='ORDERDATE')  # prioriza más recientes
    df = df.drop_duplicates(subset='ORDERNUMBER', keep='last')

    # Guardar como JSON en carpeta /process
    json_data = df.to_json(orient='records', lines=True)
    process_key = raw_key.replace("raw/", "process/").replace(".csv", ".json")

    s3.put_object(Bucket=bucket, Key=process_key, Body=json_data.encode('utf-8'))

    return {
        'statusCode': 200,
        'body': f'Archivo limpio guardado en: s3://{bucket}/{process_key}'
    }
