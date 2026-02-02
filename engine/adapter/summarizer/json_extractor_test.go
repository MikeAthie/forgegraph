package summarizer

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func TestExtractJSON_SimpleObject(t *testing.T) {
	input := `{"key": "value"}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}
	if result != input {
		t.Fatalf("result = %q, want %q", result, input)
	}
}

func TestExtractJSON_NestedBraces(t *testing.T) {
	input := `Here is the summary: {"text": "Use {curly braces} for objects", "count": 5}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}
	if !strings.Contains(result, "{curly braces}") {
		t.Fatalf("result should contain nested braces: %q", result)
	}

	var parsed map[string]any
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if parsed["text"] != "Use {curly braces} for objects" {
		t.Fatalf("text = %q, want %q", parsed["text"], "Use {curly braces} for objects")
	}
}

func TestExtractJSON_EscapedQuotes(t *testing.T) {
	input := `{"message": "He said \"hello\" to me"}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}

	var parsed map[string]string
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	want := `He said "hello" to me`
	if parsed["message"] != want {
		t.Fatalf("message = %q, want %q", parsed["message"], want)
	}
}

func TestExtractJSON_EscapedBackslash(t *testing.T) {
	input := `{"path": "C:\\Users\\test"}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}

	var parsed map[string]string
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if parsed["path"] != `C:\Users\test` {
		t.Fatalf("path = %q, want %q", parsed["path"], `C:\Users\test`)
	}
}

func TestExtractJSON_ComplexNesting(t *testing.T) {
	input := `{
		"summary": "Discussion about {APIs}",
		"facts": [
			{"key": "language", "value": "Go"},
			{"key": "syntax", "value": "uses {} for blocks"}
		],
		"metadata": {"nested": {"deep": "value"}}
	}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}

	var parsed map[string]any
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if parsed["summary"] != "Discussion about {APIs}" {
		t.Fatalf("summary = %q, want %q", parsed["summary"], "Discussion about {APIs}")
	}

	facts, ok := parsed["facts"].([]any)
	if !ok || len(facts) != 2 {
		t.Fatalf("facts should have 2 items: %#v", parsed["facts"])
	}

	metadata, ok := parsed["metadata"].(map[string]any)
	if !ok {
		t.Fatalf("metadata should be an object: %#v", parsed["metadata"])
	}
	nested, ok := metadata["nested"].(map[string]any)
	if !ok || nested["deep"] != "value" {
		t.Fatalf("nested.deep = %v, want %q", nested["deep"], "value")
	}
}

func TestExtractJSON_SurroundingText(t *testing.T) {
	input := `
		I've analyzed the conversation. Here's my summary:

		{"summary": "User discussed project requirements", "facts": []}

		Let me know if you need more details.
	`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}
	if !strings.HasPrefix(result, "{") || !strings.HasSuffix(result, "}") {
		t.Fatalf("result should start with { and end with }: %q", result)
	}

	var parsed map[string]any
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if parsed["summary"] != "User discussed project requirements" {
		t.Fatalf("summary = %q, want %q", parsed["summary"], "User discussed project requirements")
	}
}

func TestExtractJSON_NoJSON(t *testing.T) {
	input := "This is just plain text without any JSON"
	_, err := ExtractJSON(input)
	if !errors.Is(err, ErrNoJSONFound) {
		t.Fatalf("error = %v, want ErrNoJSONFound", err)
	}
}

func TestExtractJSON_UnbalancedBraces(t *testing.T) {
	input := `{"key": "value"`
	_, err := ExtractJSON(input)
	if !errors.Is(err, ErrUnbalancedBraces) {
		t.Fatalf("error = %v, want ErrUnbalancedBraces", err)
	}
}

func TestExtractJSON_UnbalancedNested(t *testing.T) {
	input := `{"outer": {"inner": "value"}`
	_, err := ExtractJSON(input)
	if !errors.Is(err, ErrUnbalancedBraces) {
		t.Fatalf("error = %v, want ErrUnbalancedBraces", err)
	}
}

func TestExtractJSON_InvalidJSON(t *testing.T) {
	input := `{key without quotes: value}`
	_, err := ExtractJSON(input)
	if !errors.Is(err, ErrInvalidJSON) {
		t.Fatalf("error = %v, want ErrInvalidJSON", err)
	}
}

func TestExtractJSON_EmptyObject(t *testing.T) {
	input := `{}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}
	if result != "{}" {
		t.Fatalf("result = %q, want %q", result, "{}")
	}
}

func TestExtractJSON_BracesInsideString(t *testing.T) {
	input := `{"template": "Hello {name}, your balance is {balance}"}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}

	var parsed map[string]string
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	want := "Hello {name}, your balance is {balance}"
	if parsed["template"] != want {
		t.Fatalf("template = %q, want %q", parsed["template"], want)
	}
}

func TestExtractJSON_MultipleObjects_ReturnsFirst(t *testing.T) {
	input := `{"first": 1} {"second": 2}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}

	var parsed map[string]int
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if parsed["first"] != 1 {
		t.Fatalf("first = %d, want 1", parsed["first"])
	}
	if strings.Contains(result, "second") {
		t.Fatalf("result should not contain second object: %q", result)
	}
}

func TestExtractJSON_UnicodeContent(t *testing.T) {
	input := `{"greeting": "こんにちは", "emoji": "🎉"}`
	result, err := ExtractJSON(input)
	if err != nil {
		t.Fatalf("ExtractJSON returned error: %v", err)
	}

	var parsed map[string]string
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if parsed["greeting"] != "こんにちは" {
		t.Fatalf("greeting = %q, want %q", parsed["greeting"], "こんにちは")
	}
	if parsed["emoji"] != "🎉" {
		t.Fatalf("emoji = %q, want %q", parsed["emoji"], "🎉")
	}
}

func TestExtractJSON_WhitespaceOnly(t *testing.T) {
	input := "   \n\t  "
	_, err := ExtractJSON(input)
	if !errors.Is(err, ErrNoJSONFound) {
		t.Fatalf("error = %v, want ErrNoJSONFound", err)
	}
}

// --- ExtractJSONArray Tests ---

func TestExtractJSONArray_SimpleArray(t *testing.T) {
	input := `[1, 2, 3]`
	result, err := ExtractJSONArray(input)
	if err != nil {
		t.Fatalf("ExtractJSONArray returned error: %v", err)
	}
	if result != input {
		t.Fatalf("result = %q, want %q", result, input)
	}
}

func TestExtractJSONArray_ObjectArray(t *testing.T) {
	input := `[{"name": "Alice"}, {"name": "Bob"}]`
	result, err := ExtractJSONArray(input)
	if err != nil {
		t.Fatalf("ExtractJSONArray returned error: %v", err)
	}

	var parsed []map[string]string
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if len(parsed) != 2 {
		t.Fatalf("len(parsed) = %d, want 2", len(parsed))
	}
	if parsed[0]["name"] != "Alice" {
		t.Fatalf("parsed[0].name = %q, want %q", parsed[0]["name"], "Alice")
	}
}

func TestExtractJSONArray_NestedArrays(t *testing.T) {
	input := `[[1, 2], [3, 4], [5, 6]]`
	result, err := ExtractJSONArray(input)
	if err != nil {
		t.Fatalf("ExtractJSONArray returned error: %v", err)
	}

	var parsed [][]int
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if len(parsed) != 3 {
		t.Fatalf("len(parsed) = %d, want 3", len(parsed))
	}
}

func TestExtractJSONArray_SurroundingText(t *testing.T) {
	input := `Here are the results: [{"id": 1}, {"id": 2}] - that's all.`
	result, err := ExtractJSONArray(input)
	if err != nil {
		t.Fatalf("ExtractJSONArray returned error: %v", err)
	}

	var parsed []map[string]int
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if len(parsed) != 2 {
		t.Fatalf("len(parsed) = %d, want 2", len(parsed))
	}
}

func TestExtractJSONArray_NoArray(t *testing.T) {
	input := "No arrays here"
	_, err := ExtractJSONArray(input)
	if !errors.Is(err, ErrNoJSONFound) {
		t.Fatalf("error = %v, want ErrNoJSONFound", err)
	}
}

func TestExtractJSONArray_UnbalancedBrackets(t *testing.T) {
	input := `[1, 2, 3`
	_, err := ExtractJSONArray(input)
	if !errors.Is(err, ErrUnbalancedBraces) {
		t.Fatalf("error = %v, want ErrUnbalancedBraces", err)
	}
}

func TestExtractJSONArray_BracketsInString(t *testing.T) {
	input := `["array notation: [1,2,3]", "another [item]"]`
	result, err := ExtractJSONArray(input)
	if err != nil {
		t.Fatalf("ExtractJSONArray returned error: %v", err)
	}

	var parsed []string
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v", err)
	}
	if len(parsed) != 2 {
		t.Fatalf("len(parsed) = %d, want 2", len(parsed))
	}
	if parsed[0] != "array notation: [1,2,3]" {
		t.Fatalf("parsed[0] = %q, want %q", parsed[0], "array notation: [1,2,3]")
	}
}

// --- stripMarkdownCodeBlocks Tests ---

func TestStripMarkdownCodeBlocks_JSONBlock(t *testing.T) {
	input := "Here's the JSON:\n```json\n{\"key\": \"value\"}\n```\nThat's all."
	result := stripMarkdownCodeBlocks(input)
	if result != `{"key": "value"}` {
		t.Fatalf("result = %q, want %q", result, `{"key": "value"}`)
	}
}

func TestStripMarkdownCodeBlocks_PlainBlock(t *testing.T) {
	input := "```\n{\"key\": \"value\"}\n```"
	result := stripMarkdownCodeBlocks(input)
	if result != `{"key": "value"}` {
		t.Fatalf("result = %q, want %q", result, `{"key": "value"}`)
	}
}

func TestStripMarkdownCodeBlocks_NoBlock(t *testing.T) {
	input := `{"key": "value"}`
	result := stripMarkdownCodeBlocks(input)
	if result != input {
		t.Fatalf("result = %q, want %q", result, input)
	}
}

func TestStripMarkdownCodeBlocks_MultilineJSON(t *testing.T) {
	input := "```json\n{\n  \"key\": \"value\",\n  \"nested\": {\n    \"a\": 1\n  }\n}\n```"
	result := stripMarkdownCodeBlocks(input)

	var parsed map[string]any
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		t.Fatalf("result is not valid JSON: %v\nresult: %q", err, result)
	}
	if parsed["key"] != "value" {
		t.Fatalf("key = %q, want %q", parsed["key"], "value")
	}
}

// --- findMatchingBrace Tests ---

func TestFindMatchingBrace_Simple(t *testing.T) {
	input := `{"key": "value"}`
	end, err := findMatchingBrace(input, 0)
	if err != nil {
		t.Fatalf("findMatchingBrace returned error: %v", err)
	}
	if end != len(input)-1 {
		t.Fatalf("end = %d, want %d", end, len(input)-1)
	}
}

func TestFindMatchingBrace_Nested(t *testing.T) {
	input := `{"outer": {"inner": "value"}}`
	end, err := findMatchingBrace(input, 0)
	if err != nil {
		t.Fatalf("findMatchingBrace returned error: %v", err)
	}
	if end != len(input)-1 {
		t.Fatalf("end = %d, want %d", end, len(input)-1)
	}
}

func TestFindMatchingBrace_InvalidStart(t *testing.T) {
	input := `"not a brace"`
	_, err := findMatchingBrace(input, 0)
	if err == nil {
		t.Fatal("expected error for invalid start position")
	}
}

func TestFindMatchingBrace_OutOfBounds(t *testing.T) {
	input := `{}`
	_, err := findMatchingBrace(input, 100)
	if err == nil {
		t.Fatal("expected error for out of bounds start")
	}
}

func TestFindMatchingBrace_NegativeStart(t *testing.T) {
	input := `{}`
	_, err := findMatchingBrace(input, -1)
	if err == nil {
		t.Fatal("expected error for negative start")
	}
}

// --- Benchmark Tests ---

func BenchmarkExtractJSON_Simple(b *testing.B) {
	input := `{"key": "value", "number": 42}`
	for i := 0; i < b.N; i++ {
		_, _ = ExtractJSON(input)
	}
}

func BenchmarkExtractJSON_Complex(b *testing.B) {
	input := `Here is a complex response with lots of text before the JSON:

	{"summary": "This is a detailed summary of the conversation that took place",
	 "facts": [
		{"key": "user_name", "value": "Alice", "confidence": 0.95},
		{"key": "topic", "value": "Project planning", "confidence": 0.88},
		{"key": "action_items", "value": "Review docs, schedule meeting", "confidence": 0.72}
	 ],
	 "metadata": {"model": "claude", "tokens": 1500}}

	And some text after as well.`

	for i := 0; i < b.N; i++ {
		_, _ = ExtractJSON(input)
	}
}

func BenchmarkExtractJSON_DeepNesting(b *testing.B) {
	input := `{"l1": {"l2": {"l3": {"l4": {"l5": {"value": "deep"}}}}}}`
	for i := 0; i < b.N; i++ {
		_, _ = ExtractJSON(input)
	}
}

func BenchmarkExtractJSON_LargeStrings(b *testing.B) {
	largeString := strings.Repeat("Hello {world} ", 100)
	input := `{"content": "` + largeString + `", "count": 100}`
	for i := 0; i < b.N; i++ {
		_, _ = ExtractJSON(input)
	}
}
