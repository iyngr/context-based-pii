import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest, { params }: { params: Promise<{ slug: string[] }> }) {
    return handleRequest(request, params, 'GET');
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ slug: string[] }> }) {
    return handleRequest(request, params, 'POST');
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ slug: string[] }> }) {
    return handleRequest(request, params, 'PUT');
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ slug: string[] }> }) {
    return handleRequest(request, params, 'DELETE');
}

async function handleRequest(request: NextRequest, params: Promise<{ slug: string[] }>, method: string) {
    const resolvedParams = await params;
    const BACKEND_SERVICE_URL = process.env.BACKEND_SERVICE_URL || 'http://localhost:8081';
    
    // Build the target URL by joining the slug array
    const path = resolvedParams.slug ? resolvedParams.slug.join('/') : '';
    const targetUrl = `${BACKEND_SERVICE_URL}/${path}`;
    
    // Get search params from the original request
    const searchParams = request.nextUrl.searchParams.toString();
    const finalUrl = searchParams ? `${targetUrl}?${searchParams}` : targetUrl;
    
    console.log(`Proxying request: ${method} ${request.url} -> ${finalUrl}`);
    
    try {
        // Prepare headers
        const headers = new Headers();
        
        // Copy relevant headers from the original request
        const headersToProxy = ['authorization', 'content-type', 'user-agent'];
        headersToProxy.forEach(headerName => {
            const headerValue = request.headers.get(headerName);
            if (headerValue) {
                headers.set(headerName, headerValue);
            }
        });
        
        // Prepare the fetch options
        const fetchOptions: RequestInit = {
            method,
            headers,
        };
        
        // Add body for POST/PUT requests
        if (method === 'POST' || method === 'PUT') {
            const body = await request.text();
            if (body) {
                fetchOptions.body = body;
            }
        }
        
        // Make the request to the backend
        const response = await fetch(finalUrl, fetchOptions);
        
        // Get the response body
        const responseBody = await response.text();
        
        // Create the response with the same status and headers
        const nextResponse = new NextResponse(responseBody, {
            status: response.status,
            statusText: response.statusText,
        });
        
        // Copy response headers
        response.headers.forEach((value, name) => {
            // Skip certain headers that should not be proxied
            if (!['content-encoding', 'content-length', 'transfer-encoding'].includes(name.toLowerCase())) {
                nextResponse.headers.set(name, value);
            }
        });
        
        return nextResponse;
        
    } catch (error) {
        console.error('Proxy error:', error);
        return new NextResponse('Proxy error', { status: 500 });
    }
}