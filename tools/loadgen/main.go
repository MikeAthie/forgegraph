package main

import (
	"context"
	"fmt"
	"os"
	"strings"
)

func main() {
	cfg, err := ParseConfig(os.Args[1:])
	if err != nil {
		fmt.Fprintf(os.Stderr, "loadgen: %v\n", err)
		os.Exit(2)
	}
	report, err := Run(context.Background(), cfg, os.Args)
	if err != nil {
		fmt.Fprintf(os.Stderr, "loadgen failed: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("loadgen completed: passed=%t report=%s\n", report.Passed, strings.Join(report.ReportPaths, ", "))
}
