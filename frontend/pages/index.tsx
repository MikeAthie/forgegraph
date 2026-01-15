import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../contexts/AuthContext";
import { Badge, Button } from "@/components/ui";

// Animated typing effect for hero
const useTypingEffect = (words: string[], typingSpeed = 100, deletingSpeed = 50, pauseTime = 2000) => {
  const [currentWordIndex, setCurrentWordIndex] = useState(0);
  const [currentText, setCurrentText] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    const word = words[currentWordIndex];

    const timeout = setTimeout(() => {
      if (!isDeleting) {
        if (currentText.length < word.length) {
          setCurrentText(word.slice(0, currentText.length + 1));
        } else {
          setTimeout(() => setIsDeleting(true), pauseTime);
        }
      } else {
        if (currentText.length > 0) {
          setCurrentText(word.slice(0, currentText.length - 1));
        } else {
          setIsDeleting(false);
          setCurrentWordIndex((prev) => (prev + 1) % words.length);
        }
      }
    }, isDeleting ? deletingSpeed : typingSpeed);

    return () => clearTimeout(timeout);
  }, [currentText, isDeleting, currentWordIndex, words, typingSpeed, deletingSpeed, pauseTime]);

  return currentText;
};

// Animated counter hook
const useCounter = (end: number, duration = 2000, startOnView = true) => {
  const [count, setCount] = useState(0);
  const [hasStarted, setHasStarted] = useState(!startOnView);

  useEffect(() => {
    if (!hasStarted) return;

    let startTime: number;
    const step = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      setCount(Math.floor(progress * end));
      if (progress < 1) {
        requestAnimationFrame(step);
      }
    };
    requestAnimationFrame(step);
  }, [end, duration, hasStarted]);

  return { count, start: () => setHasStarted(true) };
};

// Feature icons as simple SVG components
const WorkflowIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
  </svg>
);

const BoltIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
  </svg>
);

const CodeIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
  </svg>
);

const ShieldIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
  </svg>
);

const CpuIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25zm.75-12h9v9h-9v-9z" />
  </svg>
);

const UsersIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
  </svg>
);

const features = [
  {
    icon: WorkflowIcon,
    title: "Drag, Drop, Done",
    description: "Build your first AI agent in minutes. Just connect the blocks and watch it work. No PhD required.",
  },
  {
    icon: BoltIcon,
    title: "Blazing Fast",
    description: "Your agents run at lightning speed. Handle thousands of requests without breaking a sweat.",
  },
  {
    icon: CodeIcon,
    title: "Code When You Want",
    description: "Start visual, go pro when ready. Full API access for when you need that extra power.",
  },
  {
    icon: ShieldIcon,
    title: "You Stay in Control",
    description: "Add approval steps for important decisions. Your AI asks before it acts on the big stuff.",
  },
  {
    icon: CpuIcon,
    title: "Use Any AI Model",
    description: "GPT-4, Claude, Llama, or your own models. Switch anytime without rebuilding anything.",
  },
  {
    icon: UsersIcon,
    title: "Build Together",
    description: "Share your best prompts and workflows with your team. Everyone levels up together.",
  },
];

// Animated workflow node component
const AnimatedNode = ({
  color,
  icon,
  title,
  subtitle,
  delay = 0,
  isActive = false
}: {
  color: string;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  delay?: number;
  isActive?: boolean;
}) => (
  <div
    className={`
      w-44 rounded-xl p-4 text-center transition-all duration-500 transform
      ${isActive ? 'scale-105 shadow-lg' : 'scale-100'}
      ${color.includes('violet') ? 'bg-violet-500/10 border-2 border-violet-500' : ''}
      ${color.includes('amber') ? 'bg-amber-500/10 border-2 border-amber-500' : ''}
      ${color.includes('blue') ? 'bg-blue-500/10 border-2 border-blue-500' : ''}
      ${color.includes('emerald') ? 'bg-emerald-500/10 border-2 border-emerald-500' : ''}
      ${color.includes('rose') ? 'bg-rose-500/10 border-2 border-rose-500' : ''}
    `}
    style={{
      animationDelay: `${delay}ms`,
      animation: 'fadeInUp 0.6s ease-out forwards',
      opacity: 0,
    }}
  >
    <div className={`w-10 h-10 rounded-lg mx-auto mb-2 flex items-center justify-center transition-all duration-300 ${
      isActive ? 'scale-110' : ''
    } ${color}`}>
      {icon}
    </div>
    <p className="font-semibold text-sm">{title}</p>
    <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
    {isActive && (
      <div className="mt-2 flex justify-center">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
        </span>
      </div>
    )}
  </div>
);

// Animated connection line
const ConnectionLine = ({ isActive = false, delay = 0 }: { isActive?: boolean; delay?: number }) => (
  <div
    className="hidden lg:flex items-center w-16"
    style={{
      animationDelay: `${delay}ms`,
      animation: 'fadeIn 0.4s ease-out forwards',
      opacity: 0,
    }}
  >
    <div className={`h-0.5 flex-1 transition-colors duration-300 ${isActive ? 'bg-primary' : 'bg-border'}`}>
      <div
        className={`h-full bg-primary transition-all duration-1000 ${isActive ? 'w-full' : 'w-0'}`}
      />
    </div>
    <div className={`w-0 h-0 border-t-4 border-b-4 border-l-6 border-transparent transition-colors duration-300 ${
      isActive ? 'border-l-primary' : 'border-l-border'
    }`} style={{ borderLeftWidth: '6px' }} />
  </div>
);

export default function Home() {
  const { isAuthenticated } = useAuth();
  const [activeNode, setActiveNode] = useState(0);
  const [isVisible, setIsVisible] = useState(false);

  const typedText = useTypingEffect([
    "In Minutes",
    "Without Code",
    "That Just Work",
    "Your Way",
  ], 80, 40, 2500);

  // Animate workflow nodes
  useEffect(() => {
    setIsVisible(true);
    const interval = setInterval(() => {
      setActiveNode((prev) => (prev + 1) % 5);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  // Floating particles for hero background
  const particles = Array.from({ length: 20 }, (_, i) => ({
    id: i,
    size: Math.random() * 4 + 2,
    x: Math.random() * 100,
    y: Math.random() * 100,
    duration: Math.random() * 20 + 10,
    delay: Math.random() * 5,
  }));

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      {/* CSS Animations */}
      <style jsx global>{`
        @keyframes fadeInUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        @keyframes float {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          50% { transform: translateY(-20px) rotate(5deg); }
        }

        @keyframes pulse-glow {
          0%, 100% {
            box-shadow: 0 0 20px rgba(99, 102, 241, 0.3);
          }
          50% {
            box-shadow: 0 0 40px rgba(99, 102, 241, 0.6), 0 0 60px rgba(99, 102, 241, 0.3);
          }
        }

        @keyframes gradient-x {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }

        @keyframes particle-float {
          0%, 100% {
            transform: translate(0, 0) scale(1);
            opacity: 0.3;
          }
          25% {
            transform: translate(10px, -30px) scale(1.1);
            opacity: 0.6;
          }
          50% {
            transform: translate(-5px, -60px) scale(1);
            opacity: 0.4;
          }
          75% {
            transform: translate(15px, -30px) scale(0.9);
            opacity: 0.5;
          }
        }

        .animate-gradient {
          background-size: 200% 200%;
          animation: gradient-x 3s ease infinite;
        }

        .glow-effect {
          animation: pulse-glow 2s ease-in-out infinite;
        }
      `}</style>

      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-lg border-b border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center glow-effect">
                <svg className="w-5 h-5 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <span className="text-xl font-bold">ForgeGraph</span>
            </div>
            <div className="flex items-center gap-4">
              {isAuthenticated ? (
                <Button asChild>
                  <Link href="/graphs">Dashboard</Link>
                </Button>
              ) : (
                <>
                  <Button variant="ghost" asChild>
                    <Link href="/login">Sign in</Link>
                  </Button>
                  <Button asChild className="glow-effect">
                    <Link href="/register">Get Started</Link>
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8 relative overflow-hidden min-h-[90vh] flex items-center">
        {/* Animated background */}
        <div className="absolute inset-0 -z-10">
          {/* Gradient orbs */}
          <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-primary/30 rounded-full blur-[100px] animate-pulse" />
          <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-violet-500/20 rounded-full blur-[80px] animate-pulse" style={{ animationDelay: '1s' }} />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-indigo-500/10 rounded-full blur-[120px]" />

          {/* Floating particles */}
          {particles.map((particle) => (
            <div
              key={particle.id}
              className="absolute rounded-full bg-primary/40"
              style={{
                width: particle.size,
                height: particle.size,
                left: `${particle.x}%`,
                top: `${particle.y}%`,
                animation: `particle-float ${particle.duration}s ease-in-out infinite`,
                animationDelay: `${particle.delay}s`,
              }}
            />
          ))}

          {/* Grid overlay */}
          <div
            className="absolute inset-0 opacity-[0.03]"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' width='32' height='32' fill='none' stroke='rgb(99 102 241 / 0.3)'%3e%3cpath d='M0 .5H31.5V32'/%3e%3c/svg%3e")`,
            }}
          />
        </div>

        <div className="max-w-5xl mx-auto text-center relative">
          <div
            className={`transition-all duration-1000 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}
          >
            <Badge variant="secondary" className="mb-6 px-4 py-1.5 text-sm animate-bounce">
              <span className="relative flex h-2 w-2 mr-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
              </span>
              Currently in Beta
            </Badge>
          </div>

          <h1
            className={`text-4xl sm:text-5xl lg:text-7xl font-bold tracking-tight transition-all duration-1000 delay-200 ${
              isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
            }`}
          >
            Create AI Agents
            <span className="block mt-2 h-[1.2em] bg-linear-to-r from-primary via-violet-500 to-fuchsia-500 bg-clip-text text-transparent animate-gradient bg-[length:200%_auto]">
              {typedText}
              <span className="animate-pulse">|</span>
            </span>
          </h1>

          <p
            className={`mt-8 text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto transition-all duration-1000 delay-400 ${
              isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
            }`}
          >
            Want to build your own AI agents? Just drag, drop, and connect.
            No complex setup. No coding headaches. Just results.
          </p>

          <div
            className={`mt-10 flex flex-col sm:flex-row items-center justify-center gap-4 transition-all duration-1000 delay-500 ${
              isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'
            }`}
          >
            <Button size="lg" className="w-full sm:w-auto text-base px-8 group glow-effect" asChild>
              <Link href="/register">
                Try It Free
                <svg className="ml-2 w-4 h-4 transition-transform group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </Link>
            </Button>
            <Button size="lg" variant="outline" className="w-full sm:w-auto text-base px-8 group" asChild>
              <Link href="#demo">
                See How It Works
                <svg className="ml-2 w-4 h-4 transition-transform group-hover:translate-y-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
              </Link>
            </Button>
          </div>

          {/* Scroll indicator */}
          <div className={`mt-16 flex justify-center transition-all duration-1000 delay-700 ${
            isVisible ? 'opacity-100' : 'opacity-0'
          }`}>
            <div className="flex flex-col items-center gap-2 text-muted-foreground animate-bounce">
              <span className="text-xs uppercase tracking-wider">Scroll to explore</span>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
            </div>
          </div>
        </div>
      </section>

      {/* Live Workflow Demo Section */}
      <section id="demo" className="py-24 px-4 sm:px-6 lg:px-8 bg-muted/30 relative overflow-hidden scroll-mt-20">
        <div className="absolute inset-0 opacity-[0.02]" style={{
          backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' width='32' height='32' fill='none' stroke='rgb(0 0 0 / 0.5)'%3e%3cpath d='M0 .5H31.5V32'/%3e%3c/svg%3e")`,
        }} />

        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <Badge variant="outline" className="mb-4">See It In Action</Badge>
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold">This Is How Simple It Is</h2>
            <p className="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">
              Watch your agent process a request step by step. Every action is visible and traceable.
            </p>
          </div>

          {/* Animated workflow */}
          <div className="relative bg-background rounded-2xl border border-border p-8 lg:p-12 shadow-2xl">
            <div className="flex flex-col lg:flex-row items-center justify-center gap-4 lg:gap-0">
              <AnimatedNode
                color="bg-violet-500"
                icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>}
                title="Analyze Input"
                subtitle="GPT-4 Turbo"
                delay={0}
                isActive={activeNode === 0}
              />
              <ConnectionLine isActive={activeNode >= 1} delay={100} />

              <AnimatedNode
                color="bg-amber-500"
                icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 15L12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" /></svg>}
                title="Route Intent"
                subtitle="Conditional"
                delay={200}
                isActive={activeNode === 1}
              />
              <ConnectionLine isActive={activeNode >= 2} delay={300} />

              <AnimatedNode
                color="bg-blue-500"
                icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" /></svg>}
                title="Fetch Data"
                subtitle="REST API"
                delay={400}
                isActive={activeNode === 2}
              />
              <ConnectionLine isActive={activeNode >= 3} delay={500} />

              <AnimatedNode
                color="bg-emerald-500"
                icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 00-3.7-3.7 48.678 48.678 0 00-7.324 0 4.006 4.006 0 00-3.7 3.7c-.017.22-.032.441-.046.662M19.5 12l3-3m-3 3l-3-3m-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 003.7 3.7 48.656 48.656 0 007.324 0 4.006 4.006 0 003.7-3.7c.017-.22.032-.441.046-.662M4.5 12l3 3m-3-3l-3 3" /></svg>}
                title="Transform"
                subtitle="JSON Parser"
                delay={600}
                isActive={activeNode === 3}
              />
              <ConnectionLine isActive={activeNode >= 4} delay={700} />

              <AnimatedNode
                color="bg-rose-500"
                icon={<svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                title="Complete"
                subtitle="Output"
                delay={800}
                isActive={activeNode === 4}
              />
            </div>

            {/* Live stats */}
            <div className="mt-8 pt-6 border-t border-border">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                <div className="bg-muted/50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-primary">
                    {activeNode + 1}<span className="text-muted-foreground">/5</span>
                  </div>
                  <div className="text-xs text-muted-foreground">Nodes Complete</div>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-emerald-500">847ms</div>
                  <div className="text-xs text-muted-foreground">Total Latency</div>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-blue-500">156</div>
                  <div className="text-xs text-muted-foreground">Tokens Used</div>
                </div>
                <div className="bg-muted/50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-amber-500">$0.004</div>
                  <div className="text-xs text-muted-foreground">Run Cost</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="py-24 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold">Why You&apos;ll Love It</h2>
            <p className="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">
              We removed all the annoying parts of building AI agents. Here&apos;s what&apos;s left.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {features.map((feature, index) => (
              <div
                key={feature.title}
                className="group relative bg-background rounded-2xl border border-border p-6 hover:border-primary/50 hover:shadow-xl hover:shadow-primary/10 transition-all duration-500 hover:-translate-y-2"
                style={{
                  animation: 'fadeInUp 0.6s ease-out forwards',
                  animationDelay: `${index * 100}ms`,
                  opacity: 0,
                }}
              >
                <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center text-primary mb-4 group-hover:bg-primary group-hover:text-primary-foreground group-hover:scale-110 transition-all duration-300">
                  <feature.icon />
                </div>
                <h3 className="text-xl font-semibold mb-2 group-hover:text-primary transition-colors">{feature.title}</h3>
                <p className="text-muted-foreground text-sm leading-relaxed">{feature.description}</p>

                {/* Hover effect line */}
                <div className="absolute bottom-0 left-0 h-1 bg-primary rounded-b-2xl transition-all duration-300 w-0 group-hover:w-full" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Code + Visual Section */}
      <section className="py-24 px-4 sm:px-6 lg:px-8 bg-muted/30">
        <div className="max-w-6xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <Badge variant="secondary" className="mb-4">For the Curious Ones</Badge>
              <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold mb-6">
                See What Your
                <span className="block text-primary">Agent Is Thinking</span>
              </h2>
              <p className="text-lg text-muted-foreground mb-8">
                Ever wonder what happened inside that AI call? Now you can see everything.
                Every step, every decision, every millisecond.
              </p>
              <ul className="space-y-4">
                {[
                  "See exactly what each step did",
                  "Spot problems instantly",
                  "Retry failed steps with one click",
                  "Share traces with your team",
                ].map((item, index) => (
                  <li
                    key={item}
                    className="flex items-center gap-3 text-sm"
                    style={{
                      animation: 'fadeInUp 0.5s ease-out forwards',
                      animationDelay: `${index * 100 + 300}ms`,
                      opacity: 0,
                    }}
                  >
                    <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center">
                      <svg className="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {/* Code preview with animation */}
            <div className="bg-[#0d1117] rounded-2xl border border-border overflow-hidden shadow-2xl transform hover:scale-[1.02] transition-transform duration-300">
              <div className="flex items-center gap-2 px-4 py-3 bg-[#161b22] border-b border-border">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-[#ff5f56]" />
                  <div className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
                  <div className="w-3 h-3 rounded-full bg-[#27c93f]" />
                </div>
                <span className="text-xs text-muted-foreground ml-2 font-mono">run_trace.json</span>
                <div className="ml-auto flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
                  </span>
                  <span className="text-xs text-emerald-400">Live</span>
                </div>
              </div>
              <pre className="p-4 text-sm overflow-x-auto">
                <code className="text-gray-300">
                  <span className="text-gray-500">{"{"}</span>{"\n"}
                  {"  "}<span className="text-violet-400">&quot;run_id&quot;</span><span className="text-gray-500">:</span> <span className="text-emerald-400">&quot;run_8x7kL2mN&quot;</span><span className="text-gray-500">,</span>{"\n"}
                  {"  "}<span className="text-violet-400">&quot;status&quot;</span><span className="text-gray-500">:</span> <span className="text-emerald-400">&quot;completed&quot;</span><span className="text-gray-500">,</span>{"\n"}
                  {"  "}<span className="text-violet-400">&quot;duration_ms&quot;</span><span className="text-gray-500">:</span> <span className="text-amber-400">2847</span><span className="text-gray-500">,</span>{"\n"}
                  {"  "}<span className="text-violet-400">&quot;nodes&quot;</span><span className="text-gray-500">:</span> <span className="text-gray-500">[</span>{"\n"}
                  {"    {"}{"\n"}
                  {"      "}<span className="text-violet-400">&quot;id&quot;</span><span className="text-gray-500">:</span> <span className="text-emerald-400">&quot;analyze_request&quot;</span><span className="text-gray-500">,</span>{"\n"}
                  {"      "}<span className="text-violet-400">&quot;type&quot;</span><span className="text-gray-500">:</span> <span className="text-emerald-400">&quot;prompt&quot;</span><span className="text-gray-500">,</span>{"\n"}
                  {"      "}<span className="text-violet-400">&quot;model&quot;</span><span className="text-gray-500">:</span> <span className="text-emerald-400">&quot;gpt-4-turbo&quot;</span><span className="text-gray-500">,</span>{"\n"}
                  {"      "}<span className="text-violet-400">&quot;latency_ms&quot;</span><span className="text-gray-500">:</span> <span className="text-amber-400">1823</span>{"\n"}
                  {"    }"}{"\n"}
                  {"  "}<span className="text-gray-500">]</span>{"\n"}
                  <span className="text-gray-500">{"}"}</span>
                </code>
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section with animated counters */}
      <section className="py-24 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold">Built to Handle Anything</h2>
            <p className="mt-4 text-lg text-muted-foreground">From your first agent to your millionth request</p>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              { value: "<10", suffix: "ms", label: "Response Time" },
              { value: "10", suffix: "k+", label: "Parallel Agents" },
              { value: "99.9", suffix: "%", label: "Uptime" },
              { value: "100", suffix: "%", label: "Open Source" },
            ].map((stat, index) => (
              <div
                key={stat.label}
                className="text-center group"
                style={{
                  animation: 'fadeInUp 0.6s ease-out forwards',
                  animationDelay: `${index * 100}ms`,
                  opacity: 0,
                }}
              >
                <div className="text-4xl sm:text-5xl lg:text-6xl font-bold bg-linear-to-r from-primary to-violet-500 bg-clip-text text-transparent group-hover:scale-110 transition-transform duration-300 inline-block">
                  {stat.value}<span className="text-2xl sm:text-3xl">{stat.suffix}</span>
                </div>
                <div className="mt-3 text-sm text-muted-foreground font-medium">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <div className="relative bg-linear-to-br from-primary/20 via-violet-500/20 to-fuchsia-500/20 rounded-3xl border border-primary/30 p-12 lg:p-16 overflow-hidden">
            {/* Animated background elements */}
            <div className="absolute inset-0 overflow-hidden">
              <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-primary/10 rounded-full blur-3xl animate-pulse" />
              <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-violet-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
            </div>

            <div className="relative">
              <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold mb-4">
                Ready to Build Your First Agent?
              </h2>
              <p className="text-lg text-muted-foreground mb-8 max-w-xl mx-auto">
                Takes 2 minutes to sign up. Your first agent could be running in 5.
                No credit card needed.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <Button size="lg" className="w-full sm:w-auto text-base px-8 glow-effect group" asChild>
                  <Link href="/register">
                    Get Started Free
                    <svg className="ml-2 w-4 h-4 transition-transform group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </Link>
                </Button>
                <Button size="lg" variant="outline" className="w-full sm:w-auto text-base px-8 bg-background/50 backdrop-blur" asChild>
                  <Link href="https://github.com/forgegraph/forgegraph" target="_blank" rel="noopener noreferrer">
                    <svg className="mr-2 w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                    </svg>
                    Star on GitHub
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
                <svg className="w-5 h-5 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <span className="font-bold">ForgeGraph</span>
            </div>

            <div className="flex items-center gap-6 text-sm text-muted-foreground">
              <Link href="/graphs" className="hover:text-primary transition-colors">Graphs</Link>
              <Link href="/prompts" className="hover:text-primary transition-colors">Prompts</Link>
              <Link href="https://github.com/forgegraph/forgegraph" className="hover:text-primary transition-colors" target="_blank" rel="noopener noreferrer">GitHub</Link>
            </div>

            <p className="text-sm text-muted-foreground">
              Built with <span className="text-primary">indigo</span> vibes
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
