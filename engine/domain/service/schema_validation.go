package service

import (
	"bytes"
	"encoding/json"
	"fmt"
	"reflect"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v5"
)

// SchemaValidator validates values against a compiled JSON schema.
type SchemaValidator struct {
	schema *jsonschema.Schema
}

// CompileSchema compiles a JSON schema from a raw schema object.
func CompileSchema(raw any) (*SchemaValidator, error) {
	if raw == nil {
		return nil, nil
	}
	rv := reflect.ValueOf(raw)
	if (rv.Kind() == reflect.Map || rv.Kind() == reflect.Slice || rv.Kind() == reflect.Ptr || rv.Kind() == reflect.Interface) && rv.IsNil() {
		return nil, nil
	}

	encoded, err := json.Marshal(raw)
	if err != nil {
		return nil, fmt.Errorf("marshal schema: %w", err)
	}

	compiler := jsonschema.NewCompiler()
	if err := compiler.AddResource("schema.json", bytes.NewReader(encoded)); err != nil {
		return nil, fmt.Errorf("add schema resource: %w", err)
	}

	schema, err := compiler.Compile("schema.json")
	if err != nil {
		return nil, fmt.Errorf("compile schema: %w", err)
	}

	return &SchemaValidator{schema: schema}, nil
}

// Validate returns validation issues for the provided value.
func (v *SchemaValidator) Validate(value any) ([]map[string]any, error) {
	if v == nil || v.schema == nil {
		return nil, nil
	}

	if err := v.schema.Validate(value); err != nil {
		validationErr, ok := err.(*jsonschema.ValidationError)
		if !ok {
			return nil, err
		}
		return flattenValidationErrors(validationErr), nil
	}

	return nil, nil
}

func flattenValidationErrors(err *jsonschema.ValidationError) []map[string]any {
	var issues []map[string]any

	var walk func(ve *jsonschema.ValidationError)
	walk = func(ve *jsonschema.ValidationError) {
		if ve == nil {
			return
		}
		issues = append(issues, map[string]any{
			"message":     ve.Message,
			"path":        splitPointer(ve.InstanceLocation),
			"schema_path": splitPointer(ve.AbsoluteKeywordLocation),
		})
		for _, cause := range ve.Causes {
			walk(cause)
		}
	}

	walk(err)
	return issues
}

func splitPointer(pointer string) []string {
	if pointer == "" {
		return nil
	}
	if hash := strings.Index(pointer, "#"); hash >= 0 {
		pointer = pointer[hash+1:]
	}
	trimmed := strings.TrimPrefix(pointer, "/")
	if trimmed == "" {
		return nil
	}
	parts := strings.Split(trimmed, "/")
	for i, part := range parts {
		part = strings.ReplaceAll(part, "~1", "/")
		part = strings.ReplaceAll(part, "~0", "~")
		parts[i] = part
	}
	return parts
}
