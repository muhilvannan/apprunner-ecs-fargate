# Domain and SSL Configuration

# ACM Certificate for custom domain
resource "aws_acm_certificate" "main" {
  domain_name       = "brewer.muhilvannan.com"
  validation_method = "DNS"

  subject_alternative_names = [
    "*.brewer.muhilvannan.com"
  ]

  tags = {
    Name = "brewer-cert"
  }
}

# Route53 Hosted Zone for brewer.muhilvannan.com
resource "aws_route53_zone" "main" {
  name = "brewer.muhilvannan.com"

  tags = {
    Name = "brewer-hosted-zone"
  }
}

# Route53 A Record for ALB
resource "aws_route53_record" "alb" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "brewer.muhilvannan.com"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# DNS Validation Records for ACM Certificate
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.main.zone_id
}

# ACM Certificate Validation
resource "aws_acm_certificate_validation" "main" {
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}
