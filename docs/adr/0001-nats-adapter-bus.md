# Use NATS for adapter job bus

We will use NATS as the message bus between the Go service and the Adapter Runtime for Preview and Download jobs. NATS is lightweight on RAM and fits the k8s deployment constraints while providing a simple pub/sub + request/reply workflow for job dispatch and results.
