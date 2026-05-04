output "instance_public_ip" {
  description = "Public IPv4 of the DeFi streaming EC2 instance."
  value       = aws_instance.pipeline.public_ip
}

output "redpanda_console_url" {
  description = "Redpanda Console endpoint."
  value       = "http://${aws_instance.pipeline.public_ip}:8080"
}
