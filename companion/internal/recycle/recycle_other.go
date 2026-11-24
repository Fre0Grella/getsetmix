//go:build !windows && !darwin

package recycle

func move(string) error { return ErrUnsupported }
