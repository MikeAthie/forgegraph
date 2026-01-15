# Internal Packages

This directory contains private application code that is not intended to be imported by other projects.

## Structure

As the engine grows, add packages here following Go conventions:

- `server/` - gRPC server implementation
- `service/` - Business logic services
- `repository/` - Data access layer
- `model/` - Internal data models
