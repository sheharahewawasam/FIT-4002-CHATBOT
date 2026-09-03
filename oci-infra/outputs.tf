output "instance_public_ip" {
  description = "Public IP address of the chatbot server"
  value       = oci_core_instance.chatbot.public_ip
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i <your-private-key> ubuntu@${oci_core_instance.chatbot.public_ip}"
}

output "api_url" {
  description = "Django API endpoint URL"
  value       = "http://${oci_core_instance.chatbot.public_ip}:8000/api/chat/"
}

output "health_check_url" {
  description = "Open this in a browser to verify the server is up"
  value       = "http://${oci_core_instance.chatbot.public_ip}:8000/admin/"
}
