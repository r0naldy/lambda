provider "aws" {
  region = var.aws_region
}

variable "aws_region" { default = "sa-east-1" }
variable "bucket_name" { default = "x-backet-cloud2" }

# 1️⃣ Crear el bucket S3
resource "aws_s3_bucket" "data_bucket" {
  bucket = var.bucket_name
}

# 2️⃣ Política de Asunción para Lambda
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = "lambda-s3-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# 3️⃣ Permisos minimalistas para el bucket
data "aws_iam_policy_document" "lambda_s3_access" {
  statement {
    effect = "Allow"
    actions = ["s3:GetObject", "s3:PutObject"]
    resources = [
      "${aws_s3_bucket.data_bucket.arn}/raw/*",
      "${aws_s3_bucket.data_bucket.arn}/process/*"
    ]
  }
}

resource "aws_iam_role_policy" "lambda_s3_policy" {
  name   = "lambda-s3-access"
  role   = aws_iam_role.lambda_role.id
  policy = data.aws_iam_policy_document.lambda_s3_access.json
}

# 4️⃣ Capa con pandas y numpy (compatible)
resource "aws_lambda_layer_version" "pandas_layer" {
  filename            = "${path.module}/lambda_layer/python_layer.zip"
  layer_name          = "pandas_numpy_layer"
  compatible_runtimes = ["python3.9"]
}

# 5️⃣ Función Lambda principal
resource "aws_lambda_function" "data_cleaner" {
  filename         = "lambda_function_payload.zip"
  function_name    = "clean_sales_data"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  source_code_hash = filebase64sha256("lambda_function_payload.zip")
  runtime          = "python3.11"
  timeout          = 30
  layers           = [aws_lambda_layer_version.pandas_layer.arn]
}

# 6️⃣ Permiso para que S3 invoque la función
resource "aws_lambda_permission" "allow_bucket" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.data_cleaner.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.data_bucket.arn
}

# 7️⃣ Evento de S3 que dispara la Lambda al subir CSV a "raw/"
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.data_bucket.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.data_cleaner.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/"
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.allow_bucket]
}
